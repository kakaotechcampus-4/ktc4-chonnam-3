"""정해진 Git SHA에서 제한된 구조와 검증한 파일 원문만 L2 입력으로 수집한다."""

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, replace
from typing import cast

import httpx
from devon_ai import contracts as c

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
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


async def _structure(
    reader: EvidenceReader, root: str, scope: EvidenceScope, settings: Settings
) -> tuple[tuple[str, ...], list[str]]:
    queue = deque([(root, "", 0)])
    files: list[str] = []
    limitations: list[str] = []
    observed = 0
    while queue:
        sha, prefix, depth = queue.popleft()
        try:
            tree = await reader.get(f"/git/trees/{sha}")
        except EvidenceReadError as error:
            if error.code != "evidence_budget_exhausted" or not files:
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
        for raw in entries:
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
                size = raw.get("size")
                if type(size) is int and size > settings.director_prepare_max_file_bytes:
                    limitations.append(f"파일 크기 상한으로 원문을 읽지 않았습니다: {path}")
                else:
                    files.append(path)
            else:
                limitations.append(f"일반 파일이 아닌 항목은 읽지 않았습니다: {path}")
        # regular_blob이 같은 부모 tree를 다시 요청하지 않도록 검증한 목록을 공유한다.
        reader.trees[sha] = valid
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
    reader = EvidenceReader(
        http_client,
        scope.full_name,
        max_requests=settings.director_prepare_max_requests,
        max_response_bytes=settings.director_evidence_max_response_bytes,
        max_total_bytes=settings.director_evidence_max_total_bytes,
        timeout_seconds=settings.director_prepare_timeout_seconds,
    )
    try:
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
