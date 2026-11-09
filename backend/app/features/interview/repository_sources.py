"""정해진 Git SHA에서 제한된 구조와 검증한 파일 원문만 L2 입력으로 수집한다."""

import asyncio
import re
from collections import deque
from dataclasses import dataclass, replace
from typing import cast

import httpx
from devon_ai import contracts as c

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.features.interview.repository_candidates import MAX_CANDIDATES, neighbor_candidates
from app.features.interview.repository_inventory import SourceInventory
from app.features.interview.repository_source_selection import (
    selection_window,
    summarized_limitations,
)
from app.features.interview.repository_structure import recursive_files
from app.features.interview.source_segments import segment_text
from app.integrations.github.evidence import EvidenceReader, EvidenceReadError
from app.integrations.llm.client import CallBudget, call_model


class SourcePreparationError(Exception):
    """원격 원문 대신 고정 코드와 실제 모델 시도만 상위 준비 작업에 전달한다."""

    def __init__(
        self,
        code: str,
        attempts: tuple[c.AttemptMetadata, ...] = (),
        *,
        failure: c.CallFailure | None = None,
        limitations: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.attempts = attempts
        self.failure = failure
        self.limitations = limitations
        super().__init__(code)


@dataclass(frozen=True)
class SourceCollection:
    item: c.DeepRepoInput
    attempts: tuple[c.AttemptMetadata, ...]
    limitations: tuple[str, ...]
    candidate_paths: tuple[str, ...] = ()
    inventory_paths: tuple[str, ...] = ()
    selection_paths: tuple[str, ...] = ()
    inventory_limitations: tuple[str, ...] = ()


# 항목 상한에 걸려도 핵심 코드가 먼저 수집되도록 같은 디렉터리 안에서 읽는 순서를 정한다.
_SOURCE_DIRS = frozenset(
    {"src", "app", "lib", "server", "backend", "api", "core", "internal", "pkg", "cmd", "main"}
)
_LOW_VALUE_DIRS = frozenset(
    {"test", "tests", "__tests__", "spec", "docs", "doc", "examples", "example", "scripts"}
)
_VENDOR_DIRS = frozenset(
    {"node_modules", "vendor", "dist", "build", "target", "out", "venv", ".venv", "__pycache__"}
)
_SOURCE_SUFFIXES = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs"}
    | {".swift", ".scala", ".c", ".cc", ".cpp", ".h", ".hpp", ".vue", ".sql"}
)


def _priority(raw: object) -> int:
    """낮을수록 먼저 읽는다. 형식이 맞지 않는 항목은 뒤에서 기존 검증이 거절한다."""
    if not isinstance(raw, dict) or type(raw.get("path")) is not str:
        return 4
    name = cast(str, raw["path"]).lower()
    if raw.get("type") == "tree":
        if name in _SOURCE_DIRS:
            return 0
        if name in _VENDOR_DIRS or name.startswith("."):
            return 4
        return 2 if name in _LOW_VALUE_DIRS else 1
    return 0 if "." + name.rsplit(".", 1)[-1] in _SOURCE_SUFFIXES else 3


async def _structure(
    reader: EvidenceReader,
    root: str,
    scope: EvidenceScope,
    settings: Settings,
    *,
    reserve_requests: int = 0,
    reserve_bytes: int = 0,
) -> tuple[tuple[str, ...], list[str]]:
    queue = deque([(root, "", 0)])
    files: list[str] = []
    limitations: list[str] = []
    observed = 0
    while queue:
        sha, prefix, depth = queue.popleft()
        try:
            if reader.requests_left <= reserve_requests or reader.bytes_left <= reserve_bytes:
                raise EvidenceReadError("evidence_budget_exhausted")
            tree = await reader.get(
                f"/git/trees/{sha}",
                max_bytes=reader.bytes_left - reserve_bytes if reserve_bytes else None,
            )
        except EvidenceReadError as error:
            if error.code not in {"evidence_budget_exhausted", "evidence_byte_limit"} or not files:
                raise
            limitations.append(
                "구조 조회 요청 또는 바이트 상한으로 일부 디렉터리는 확인하지 못했습니다."
            )
            break
        entries = None if tree is None else tree.get("tree")
        if (
            tree is None
            or tree.get("sha") != sha
            or tree.get("truncated") is not False
            or not isinstance(entries, list)
        ):
            raise EvidenceReadError("github_invalid_response")
        names: set[str] = set()
        valid: list[object] = []
        # sorted는 안정 정렬이라 같은 우선순위 안에서는 GitHub가 준 순서를 유지한다.
        for raw in sorted(entries, key=_priority):
            if not isinstance(raw, dict) or type(raw.get("path")) is not str:
                raise EvidenceReadError("github_invalid_response")
            name = cast(str, raw["path"])
            if name in names or "/" in name:
                raise EvidenceReadError("github_invalid_response")
            names.add(name)
            path = f"{prefix}/{name}" if prefix else name
            # 기존 Tool 경계와 같은 path 규칙을 구조 단계에도 적용한다.
            replace(scope, allowed_paths=frozenset({path}))
            entry_sha = raw.get("sha")
            if (
                type(entry_sha) is not str
                or len(entry_sha) != 40
                or any(character not in "0123456789abcdef" for character in entry_sha)
            ):
                raise EvidenceReadError("github_invalid_response")
            valid.append(raw)
            if observed == settings.director_prepare_max_entries:
                limitations.append("구조 항목 상한을 넘어 나머지 항목은 확인하지 못했습니다.")
                queue.clear()
                break
            observed += 1
            kind, mode = raw.get("type"), raw.get("mode")
            if kind == "tree" and mode == "040000":
                if depth < settings.director_prepare_max_depth:
                    queue.append((entry_sha, path, depth + 1))
                else:
                    limitations.append("구조 깊이 상한으로 일부 하위 파일은 확인하지 못했습니다.")
            elif kind == "blob" and mode in {"100644", "100755"}:
                # 큰 파일도 후보에 두고 원문 조회와 구간화를 별도 예산으로 제한한다.
                files.append(path)
            else:
                limitations.append(f"일반 파일이 아닌 항목은 읽지 않았습니다: {path}")
        # 일부 항목만 확인한 부모를 완전 캐시로 두면 나머지 경로가 없다고 오판한다.
        # 캐시 밖의 기존 선정 경로는 regular_blob이 전체 부모를 다시 읽게 한다.
        if len(valid) == len(entries):
            reader.trees[sha] = valid
        if (
            not prefix
            and queue
            and observed < settings.director_prepare_max_entries
            and reader.requests_left - reserve_requests >= 2
        ):
            # 재귀 응답도 원문 몫을 침범하지 않는다. 실패 시 기존 순회 몫의 절반을 남긴다.
            probe_bytes = (reader.bytes_left - reserve_bytes) // 2
            if probe_bytes > 0:
                try:
                    recursive = await recursive_files(
                        reader, root, scope, settings, max_bytes=probe_bytes
                    )
                    if recursive is not None:
                        candidates, extra = recursive
                        limitations.extend(extra)
                        if candidates:
                            return candidates, list(dict.fromkeys(limitations))
                except EvidenceReadError as error:
                    limitations.append(
                        "재귀 구조 조회를 완료하지 못해 제한된 경로별 순회를 사용합니다: "
                        f"{error.code}"
                    )
        if observed >= settings.director_prepare_max_entries:
            if queue:
                limitations.append("구조 항목 상한으로 일부 디렉터리는 확인하지 못했습니다.")
            break
    return tuple(files), limitations


async def collect_repository_sources(
    *,
    scope: EvidenceScope,
    shallow: c.ShallowRepoAnalysis,
    prompt: c.PromptSpec,
    settings: Settings,
    http_client: httpx.AsyncClient,
    budget: CallBudget,
    paths: tuple[str, ...] | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> SourceCollection:
    """경로 선택과 뒤따르는 L2 분석은 같은 CallBudget을 사용한다.

    캐시 관찰 경로를 명시하면 모델 선택 없이 해당 파일만 다시 읽는다. 전체 tree 재귀 조회,
    전역 검색, 기본 브랜치의 내용을 사용하지 않으며 파일 원문을 임의로 잘라 성공시키지 않는다.
    """
    attempts: list[c.AttemptMetadata] = attempt_sink if attempt_sink is not None else []
    limitations: list[str] = []
    sources: list[c.SourceDocument] = []
    active_path: str | None = None
    try:
        # 앱 자격은 공개 데이터 quota용이다. 사용자 저장소 token을 원문 조회로 확대하지 않는다.
        app_auth = (
            (settings.github_client_id, settings.github_client_secret)
            if settings.github_client_id or settings.github_client_secret.get_secret_value()
            else None
        )
        reader = EvidenceReader(
            http_client,
            scope.full_name,
            max_requests=settings.director_prepare_max_requests,
            max_response_bytes=settings.director_evidence_max_response_bytes,
            max_total_bytes=settings.director_evidence_max_total_bytes,
            timeout_seconds=settings.director_prepare_timeout_seconds,
            public_app_auth=app_auth,
        )
        if shallow.repository_id != scope.repository_id or shallow.head_sha != scope.git_ref:
            raise SourcePreparationError("l1_snapshot_mismatch")
        async with asyncio.timeout(settings.director_prepare_timeout_seconds):
            repository = await reader.get("")
            if (
                repository is None
                or repository.get("id") != scope.github_repo_id
                or repository.get("private") is not False
            ):
                raise SourcePreparationError("repository_unavailable")
            root = await reader.root_tree(scope.git_ref)
            if root is None:
                raise SourcePreparationError("repository_snapshot_unavailable")
            if paths is None:
                candidates, limitations = await _structure(reader, root, scope, settings)
                if not candidates:
                    raise SourcePreparationError("repository_sources_unavailable")
                llm = settings.require_llm()

                def validate(raw: object) -> tuple[str, ...]:
                    if (
                        type(raw) is not dict
                        or set(raw) != {"selected_paths"}
                        or type(raw["selected_paths"]) is not list
                    ):
                        raise c.ContractError("schema", "selected_paths")
                    selected = raw["selected_paths"]
                    if (
                        not 1 <= len(selected) <= settings.director_prepare_max_files
                        or any(type(path) is not str or path not in candidates for path in selected)
                        or len(set(selected)) != len(selected)
                    ):
                        raise c.ContractError("semantic", "source selection scope")
                    return tuple(selected)

                result = await call_model(
                    c.ModelRequest(
                        prompt=prompt,
                        payload={
                            "operation": "select",
                            "repository_id": scope.repository_id,
                            "head_sha": scope.git_ref,
                            "shallow": asdict(shallow),
                            "candidates": [{"path": path, "kind": "file"} for path in candidates],
                            "limitations": limitations,
                            "max_selected_files": settings.director_prepare_max_files,
                        },
                        schema_name="RepoDeepSourceSelection",
                        schema_version="1",
                        output_schema={
                            "type": "object",
                            "properties": {
                                "selected_paths": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": settings.director_prepare_max_files,
                                    "items": {"type": "string", "enum": list(candidates)},
                                }
                            },
                            "required": ["selected_paths"],
                            "additionalProperties": False,
                        },
                        limits=llm.call_limits(),
                        max_attempts=1,
                    ),
                    validate,
                    api_key=llm.openai_api_key,
                    base_url=llm.llm_base_url,
                    http_client=http_client,
                    budget=budget,
                    attempt_sink=attempts,
                )
                if result.data is None:
                    raise SourcePreparationError(
                        "l2_source_selection_failed",
                        tuple(attempts),
                        failure=result.failure,
                        limitations=tuple(limitations),
                    )
                paths = result.data
            if len(paths) > settings.director_prepare_max_files or len(set(paths)) != len(paths):
                raise SourcePreparationError("repository_source_limit")
            replace(scope, allowed_paths=frozenset(paths))
            for path in paths:
                active_path = path
                try:
                    blob = await reader.regular_blob(root, path)
                    if blob is None:
                        limitations.append(f"고정 ref에서 파일을 찾지 못했습니다: {path}")
                        continue
                    text = await reader.file_text(path, scope.git_ref, blob)
                    if not text.strip():
                        limitations.append(f"빈 파일은 분석 원문에서 제외했습니다: {path}")
                    elif len(text.encode("utf-8")) > settings.director_prepare_max_file_bytes:
                        limitations.append(f"파일 크기 상한으로 원문을 분석하지 않았습니다: {path}")
                    else:
                        sources.append(c.SourceDocument(path, "file", text, "entire file"))
                except EvidenceReadError as error:
                    limitations.append(
                        f"파일 원문 조회를 완료하지 못했습니다: {path}: {error.code}"
                    )
                    if error.code in {"evidence_budget_exhausted", "evidence_byte_limit"}:
                        break
            if not sources:
                raise SourcePreparationError(
                    "repository_sources_unavailable",
                    tuple(attempts),
                    limitations=tuple(limitations),
                )
            return SourceCollection(
                c.DeepRepoInput(scope.repository_id, scope.git_ref, shallow, tuple(sources)),
                tuple(attempts),
                tuple(limitations),
            )
    except (EvidenceReadError, c.ContractError) as error:
        code = error.code if isinstance(error, EvidenceReadError) else "repository_source_invalid"
        raise SourcePreparationError(
            code, tuple(attempts), limitations=tuple(limitations)
        ) from None
    except TimeoutError:
        limitations.append(f"시간 상한으로 원문 조회를 중단했습니다: {active_path or '구조'}")
        if sources:
            return SourceCollection(
                c.DeepRepoInput(scope.repository_id, scope.git_ref, shallow, tuple(sources)),
                tuple(attempts),
                tuple(limitations),
            )
        raise SourcePreparationError(
            "repository_source_timeout",
            tuple(attempts),
            limitations=tuple(limitations),
        ) from None
