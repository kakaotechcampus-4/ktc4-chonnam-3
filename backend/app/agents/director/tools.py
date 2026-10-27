"""BE가 승인한 고정 SHA·정확한 파일만 조회한다. 조회 필요성 판단과 저장은 하지 않는다."""

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Literal

import httpx
from devon_ai.contracts import ContractError, Evidence, ToolResult, VerificationRequest
from pydantic import SecretStr

from app.integrations.github.evidence import EvidenceReader, EvidenceReadError


def _path(value: object) -> None:
    if (
        type(value) is not str
        or any(character in value for character in "\\%:?#")
        or any(
            ord(character) < 32 or ord(character) == 127 or 0xD800 <= ord(character) <= 0xDFFF
            for character in value
        )
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ContractError("schema", "evidence path")


@dataclass(frozen=True)
class EvidenceScope:
    """사용자·면접·public 선택 상태는 feature service가 확인한 뒤 이 값을 만든다."""

    repository_id: str
    github_repo_id: int
    full_name: str
    git_ref: str
    allowed_paths: frozenset[str]

    def __post_init__(self) -> None:
        if (
            type(self.repository_id) is not str
            or not self.repository_id.strip()
            or type(self.github_repo_id) is not int
            or self.github_repo_id <= 0
            or type(self.full_name) is not str
            or re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", self.full_name) is None
            or self.full_name.rsplit("/", 1)[-1] in {".", ".."}
            or type(self.git_ref) is not str
            or re.fullmatch(r"[0-9a-f]{40}", self.git_ref) is None
            or type(self.allowed_paths) is not frozenset
        ):
            raise ContractError("schema", "evidence scope")
        for path in self.allowed_paths:
            _path(path)


@dataclass(frozen=True)
class EvidenceLimits:
    """모든 조회에 공유하는 명시적 상한. timeout은 read_files 실행 전체에 적용한다."""

    max_requests: int
    max_files: int
    max_response_bytes: int
    max_total_bytes: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        for value in (
            self.max_requests,
            self.max_files,
            self.max_response_bytes,
            self.max_total_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ContractError("schema", "evidence integer limits")
        try:
            valid_timeout = (
                type(self.timeout_seconds) in {int, float}
                and math.isfinite(self.timeout_seconds)
                and self.timeout_seconds > 0
            )
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ContractError("schema", "evidence timeout")


async def read_files(
    request: VerificationRequest,
    *,
    scope: EvidenceScope,
    paths: tuple[str, ...],
    limits: EvidenceLimits,
    http_client: httpx.AsyncClient,
    access_token: SecretStr | None = None,
) -> ToolResult:
    """파일·출처만 반환한다. DB ID·질문/평가 usage와 영구 저장은 service 책임이다.

    기존 generate_question은 도구를 자동 실행하지 않는다. metadata·languages·commit
    해석, 디렉터리 확장, 현재 metadata에 고정 SHA를 붙이는 처리는 이 경계에 포함하지 않는다.
    """
    if (
        type(request) is not VerificationRequest
        or type(scope) is not EvidenceScope
        or type(limits) is not EvidenceLimits
        or type(paths) is not tuple
        or (access_token is not None and not isinstance(access_token, SecretStr))
    ):
        raise ContractError("schema", "evidence inputs")
    for path in (*request.allowed_paths, *paths):
        _path(path)
    if (
        request.repository_id != scope.repository_id
        or request.git_ref != scope.git_ref
        or len(set(request.allowed_paths)) != len(request.allowed_paths)
        or len(set(paths)) != len(paths)
        or not set(request.allowed_paths).issubset(scope.allowed_paths)
        or not set(paths).issubset(request.allowed_paths)
    ):
        raise ContractError("semantic", "evidence request scope")
    if not paths:
        return ToolResult("insufficient_analysis", (), (), ("조회할 승인 파일이 없습니다.",), None)
    reader = EvidenceReader(
        http_client,
        scope.full_name,
        max_requests=limits.max_requests,
        max_response_bytes=limits.max_response_bytes,
        max_total_bytes=limits.max_total_bytes,
        timeout_seconds=limits.timeout_seconds,
    )
    items: list[Evidence] = []
    searched: list[str] = []
    limitations: list[str] = []
    pending = paths
    try:
        async with asyncio.timeout(limits.timeout_seconds):
            repository = await reader.get("", token=access_token)
            if repository is None:
                return ToolResult(
                    "insufficient_analysis", (), (), ("선택 저장소를 확인할 수 없습니다.",), None
                )
            if (
                type(repository.get("id")) is not int
                or repository["id"] != scope.github_repo_id
                or repository.get("private") is not False
                or repository.get("visibility") != "public"
                or not isinstance(repository.get("full_name"), str)
                or str(repository["full_name"]).casefold() != scope.full_name.casefold()
            ):
                raise EvidenceReadError("evidence_repository_mismatch")
            root = await reader.root_tree(scope.git_ref)
            if root is None:
                return ToolResult(
                    "insufficient_analysis", (), (), ("고정 커밋 자료를 읽을 수 없습니다.",), None
                )
            for index, path in enumerate(paths):
                pending = paths[index:]
                if index >= limits.max_files:
                    raise EvidenceReadError("evidence_file_limit")
                blob = await reader.regular_blob(root, path)
                searched.append(path)
                if blob is None:
                    continue
                content = await reader.file_text(path, scope.git_ref, blob)
                if not content.strip():
                    limitations.append(f"{path}: 평가에 사용할 텍스트가 없습니다.")
                    continue
                items.append(
                    Evidence(
                        evidence_id=None,
                        repository_id=scope.repository_id,
                        git_ref=scope.git_ref,
                        source_kind="file",
                        path=path,
                        metadata_key=None,
                        content=content,
                        tool_name="read_file",
                        start_line=1,
                        end_line=content.count("\n") + int(not content.endswith("\n")),
                    )
                )
    except (EvidenceReadError, TimeoutError) as exc:
        code = exc.code if isinstance(exc, EvidenceReadError) else "github_timeout"
        limitations.extend(f"{path}: 조회를 완료하지 못했습니다." for path in pending)
        return ToolResult("tool_error", tuple(items), tuple(searched), tuple(limitations), code)
    status: Literal["found", "insufficient_analysis", "not_found"] = (
        "found" if items else "insufficient_analysis" if limitations else "not_found"
    )
    return ToolResult(status, tuple(items), tuple(searched), tuple(limitations), None)


__all__ = ["EvidenceLimits", "EvidenceScope", "read_files"]
