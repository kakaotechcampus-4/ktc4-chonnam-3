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
    read_scopes: tuple[tuple[str, str], ...] | None = None,
    inventory: SourceInventory | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> SourceCollection:
    """경로 선택과 뒤따르는 L2 분석은 같은 CallBudget을 사용한다.

    캐시 관찰 경로를 명시하면 모델 선택 없이 해당 파일만 다시 읽는다. 고정 SHA의 유한 구조
    목록만 열거하며 전역 검색이나 기본 브랜치 내용을 사용하지 않는다. 구간 위치를 보존한다.
    """
    attempts: list[c.AttemptMetadata] = attempt_sink if attempt_sink is not None else []
    limitations: list[str] = []
    sources: list[c.SourceDocument] = []
    neighbors: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    model_candidates: tuple[str, ...] = ()
    inventory_limitations: tuple[str, ...] = ()
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
            max_response_bytes=settings.director_prepare_max_response_bytes,
            max_total_bytes=settings.director_prepare_max_total_bytes,
            timeout_seconds=settings.director_prepare_timeout_seconds,
            public_app_auth=app_auth,
        )
        if shallow.repository_id != scope.repository_id or shallow.head_sha != scope.git_ref:
            raise SourcePreparationError("l1_snapshot_mismatch")
        if inventory is not None and inventory.head_sha != scope.git_ref:
            raise SourcePreparationError("repository_inventory_mismatch")
        llm = settings.require_llm() if paths is None else None
        selection_seconds = llm.call_limits(prompt.task_name).timeout_seconds if llm else 0
        # HTTP 예산과 선정 모델 예산을 더하되 모델 대기를 HTTP 시간으로 중복 소비하지 않는다.
        # 지정 경로 재검증은 모델을 호출하지 않으므로 원래의 HTTP 상한만 갖는다.
        async with (
            asyncio.timeout(settings.director_prepare_timeout_seconds + selection_seconds),
            asyncio.timeout(settings.director_prepare_timeout_seconds) as network_timeout,
        ):
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
                # 설정된 파일 수·응답 상한을 기준으로 원문 몫을 남긴다. 작은 전체 예산에서는
                # 남은 요청·바이트의 절반까지만 예약해 최소 한 번의 구조 조회도 가능하게 한다.
                candidates, limitations = await _structure(
                    reader,
                    root,
                    scope,
                    settings,
                    reserve_requests=min(
                        settings.director_prepare_max_files, reader.requests_left // 2
                    ),
                    reserve_bytes=min(
                        reader.bytes_left // 2,
                        settings.director_prepare_max_files * reader.response_limit,
                    ),
                )
                if not candidates:
                    raise SourcePreparationError("repository_sources_unavailable")
                selection_limit = min(settings.director_prepare_max_files, reader.requests_left)
                if selection_limit == 0:
                    raise EvidenceReadError("evidence_budget_exhausted")
                assert llm is not None
                inventory_limitations = tuple(limitations)
                limitations = list(summarized_limitations(inventory_limitations))
                selection_request, model_candidates, window_notes = selection_window(
                    shallow=shallow,
                    prompt=prompt,
                    candidates=candidates,
                    limitations=tuple(limitations),
                    max_selected_files=selection_limit,
                    limits=llm.call_limits(prompt.task_name),
                    max_enum_values=settings.repository_selection_max_enum_values,
                    max_enum_characters=settings.repository_selection_max_enum_characters,
                )
                limitations.extend(window_notes)
                if not model_candidates:
                    raise SourcePreparationError(
                        "repository_selection_input_too_large",
                        limitations=tuple(limitations),
                        failure=c.CallFailure(
                            "budget", "llm_failed", "Source selection request exceeds byte limit."
                        ),
                    )

                def validate(raw: object) -> tuple[str, ...]:
                    if (
                        type(raw) is not dict
                        or set(raw) != {"selected_paths"}
                        or type(raw["selected_paths"]) is not list
                    ):
                        raise c.ContractError("schema", "selected_paths")
                    selected = raw["selected_paths"]
                    if (
                        not 1 <= len(selected) <= selection_limit
                        or any(
                            type(path) is not str or path not in model_candidates
                            for path in selected
                        )
                        or len(set(selected)) != len(selected)
                    ):
                        raise c.ContractError("semantic", "source selection scope")
                    return tuple(selected)

                deadline = network_timeout.when()
                assert deadline is not None
                network_seconds_left = max(0, deadline - asyncio.get_running_loop().time())
                network_timeout.reschedule(None)
                try:
                    result = await call_model(
                        selection_request,
                        validate,
                        api_key=llm.openai_api_key,
                        base_url=llm.llm_base_url,
                        http_client=http_client,
                        budget=budget,
                        attempt_sink=attempts,
                    )
                finally:
                    network_timeout.reschedule(
                        asyncio.get_running_loop().time() + network_seconds_left
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
            if read_scopes is not None and inventory is not None:
                # 같은 분석을 재사용할 때도 당시 보존한 구조만 후보로 삼는다.
                candidates = inventory.paths
                model_candidates = inventory.model_candidate_paths
                inventory_limitations = inventory.limitations
                limitations.extend(summarized_limitations(inventory_limitations))
            elif read_scopes is not None:
                # 캐시 재검증 때도 새 모델 호출 없이 실제 구조를 확인하되 원문 예산을 남긴다.
                try:
                    candidates, extra = await _structure(
                        reader,
                        root,
                        scope,
                        settings,
                        reserve_requests=min(len(paths), reader.requests_left // 2),
                        reserve_bytes=min(
                            reader.bytes_left // 2, len(paths) * reader.response_limit
                        ),
                    )
                    limitations.extend(summarized_limitations(tuple(extra)))
                    inventory_limitations = tuple(extra)
                except EvidenceReadError:
                    candidates = ()
                    limitations.append("추가 조회 후보 구조는 현재 예산에서 확인하지 못했습니다.")
                    inventory_limitations = (limitations[-1],)
            candidate_limit = min(MAX_CANDIDATES, max(1, settings.director_prepare_max_files * 2))
            # 실제 읽은 선정 경로도 area 채택 여부와 무관하게 재조회할 수 있어야 한다.
            neighbors = tuple(paths[:candidate_limit])
            remaining = candidate_limit - len(neighbors)
            if remaining and set(paths).issubset(candidates):
                neighbors += neighbor_candidates(candidates, paths, limit=remaining)
            replace(scope, allowed_paths=frozenset(paths))
            # 원문 외의 식별자·L1·구간 메타데이터가 차지할 입력 공간을 남겨 둔다.
            raw_source_limit = settings.director_prepare_max_source_bytes
            llm_input_limit = settings.llm_max_input_bytes or raw_source_limit
            source_bytes_left = min(raw_source_limit, llm_input_limit // 2)
            for position, path in enumerate(paths):
                active_path = path
                try:
                    blob = await reader.regular_blob(root, path)
                    if blob is None:
                        limitations.append(f"고정 ref에서 파일을 찾지 못했습니다: {path}")
                        continue
                    file_budget = (
                        source_bytes_left
                        if read_scopes is not None
                        else (source_bytes_left // (len(paths) - position))
                    )
                    expected_size = reader.blob_sizes.get(blob)
                    complete = True
                    if (
                        expected_size is not None
                        and expected_size > settings.director_prepare_max_file_bytes
                    ):
                        text, complete = await reader.file_text_prefix(
                            path,
                            scope.git_ref,
                            blob,
                            max_bytes=file_budget,
                            expected_size=expected_size,
                        )
                        if not complete:
                            limitations.append(
                                f"큰 파일에서 원문 예산 내의 앞부분만 읽었습니다: {path}; "
                                f"읽은 줄 {len(text.splitlines())}, 전체 {expected_size} bytes"
                            )
                    else:
                        text = await reader.file_text(path, scope.git_ref, blob)
                    if not complete and not text.strip():
                        limitations.append(
                            f"현재 원문 예산 안에서 완성된 텍스트 줄을 읽지 못했습니다: {path}"
                        )
                        continue
                    if read_scopes is not None:
                        chunks, notes = _cached_segments(
                            path,
                            text,
                            read_scopes,
                            source_bytes_left,
                            settings.director_prepare_max_file_bytes,
                            complete=complete,
                        )
                    else:
                        # 앞의 큰 모듈 하나가 뒤의 설정·테스트 자료를 모두 밀어내지 않게 나눈다.
                        chunks, notes = segment_text(
                            path,
                            text,
                            max_segment_bytes=settings.director_prepare_max_file_bytes,
                            total_bytes=file_budget,
                        )
                        if not complete:
                            chunks = tuple(
                                _partial_source(chunk)
                                if chunk.read_scope == "entire file"
                                else chunk
                                for chunk in chunks
                            )
                    sources.extend(chunks)
                    limitations.extend(notes)
                    source_bytes_left -= sum(len(chunk.content.encode("utf-8")) for chunk in chunks)
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
                neighbors,
                candidates,
                model_candidates,
                inventory_limitations,
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
                neighbors,
                candidates,
                model_candidates,
                inventory_limitations,
            )
        raise SourcePreparationError(
            "repository_source_timeout",
            tuple(attempts),
            limitations=tuple(limitations),
        ) from None


def _partial_source(source: c.SourceDocument) -> c.SourceDocument:
    end = len(source.content.splitlines()) + source.start_line - 1
    return replace(source, read_scope=f"lines {source.start_line}-{end}", end_line=end)
