"""고정 SHA의 L1 보조 원문. 이름은 우선순위 힌트이며 특정 구조를 필수로 하지 않는다."""

import base64
import binascii
import hashlib
import json
import re
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from urllib.parse import quote

from app.integrations.github.base import GithubApiError, RepoSupportingFile

type SnapshotRequest = Callable[[str, dict[str, str] | None], Awaitable[dict[str, object]]]
SNAPSHOT_RESPONSE_MAX_BYTES = 65536


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _priority(path: str) -> tuple[int, str]:
    name = PurePosixPath(path).name.lower()
    hinted = any(
        word in name
        for word in (
            "manifest",
            "package",
            "requirements",
            "project",
            "build",
            "config",
            "docker",
            "cargo",
            "go.mod",
        )
    )
    text_format = PurePosixPath(path).suffix.lower() in {
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".xml",
        ".md",
        ".txt",
    }
    # 전용 명칭이 없어도 실제 텍스트 파일을 후보에 남겨 비표준 배치를 지원한다.
    return (0 if hinted else 1 if text_format else 2, path)


async def collect_snapshot_context(
    full_name: str,
    sha: str,
    request: SnapshotRequest,
    *,
    max_entries: int = 256,
    max_depth: int = 2,
    max_requests: int = 16,
    max_files: int = 4,
    max_file_chars: int = 4000,
) -> tuple[tuple[str, ...], tuple[RepoSupportingFile, ...], tuple[str, ...]]:
    structure: list[str] = []
    candidates: list[tuple[str, str, int | None]] = []
    files: list[RepoSupportingFile] = []
    limitations: list[str] = []
    used = 0

    async def get(suffix: str, params: dict[str, str] | None = None) -> dict[str, object]:
        nonlocal used
        if used >= max_requests:
            raise GithubApiError("repo_unreachable")
        used += 1
        return await request(f"/repos/{full_name}{suffix}", params)

    commit = await get(f"/git/commits/{sha}")
    root = commit.get("tree")
    if commit.get("sha") != sha or not isinstance(root, dict) or not _valid_sha(root.get("sha")):
        raise GithubApiError("repo_unreachable")
    queue = deque([(str(root["sha"]), "", 0)])
    while queue and len(structure) < max_entries:
        tree_sha, prefix, depth = queue.popleft()
        # 원문을 읽을 요청도 남겨 둔다. 전체 트리를 재귀 API로 무제한 가져오지 않는다.
        if used >= max_requests - max_files:
            limitations.append("L1 구조 조회 요청 상한으로 일부 모듈은 확인하지 못했습니다.")
            break
        value = await get(f"/git/trees/{tree_sha}")
        entries = value.get("tree")
        if value.get("sha") != tree_sha or not isinstance(entries, list):
            raise GithubApiError("repo_unreachable")
        if value.get("truncated") is not False:
            limitations.append("GitHub가 반환한 구조 목록이 일부 생략되어 있습니다.")
        names: set[str] = set()
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise GithubApiError("repo_unreachable")
            name = item["path"]
            if (
                name in names
                or name in {"", ".", ".."}
                or "/" in name
                or "\\" in name
                or "\0" in name
            ):
                raise GithubApiError("repo_unreachable")
            names.add(name)
            path = f"{prefix}/{name}" if prefix else name
            if not _valid_sha(item.get("sha")):
                raise GithubApiError("repo_unreachable")
            if len(structure) == max_entries:
                limitations.append("L1 구조 항목 상한 이후의 자료는 확인하지 못했습니다.")
                break
            if item.get("type") == "tree" and item.get("mode") == "040000":
                structure.append(path + "/")
                if depth < max_depth:
                    queue.append((str(item["sha"]), path, depth + 1))
                else:
                    limitations.append(
                        f"L1 구조 깊이 상한 이후의 자료는 확인하지 못했습니다: {path}"
                    )
            elif item.get("type") == "blob" and item.get("mode") in {"100644", "100755"}:
                structure.append(path)
                if not name.lower().startswith("readme"):
                    size = item.get("size")
                    candidates.append(
                        (path, str(item["sha"]), size if type(size) is int and size >= 0 else None)
                    )
            else:
                limitations.append(f"L1에서 일반 파일이 아닌 항목은 읽지 않았습니다: {path}")
    if queue and not limitations:
        limitations.append("L1 구조 상한으로 일부 디렉터리는 확인하지 못했습니다.")

    for path, blob, size in sorted(candidates, key=lambda item: _priority(item[0])):
        if len(files) >= max_files or used >= max_requests:
            break
        if size is not None:
            # 필수 JSON 필드와 base64만으로도 상한을 넘으면 실제 요청을 소비하지 않는다.
            # 추가 메타데이터·줄 감싸기 때문에 이 검사 통과가 수신 성공을 보장하지는 않는다.
            minimum = len(
                json.dumps(
                    {
                        "type": "file",
                        "path": path,
                        "sha": blob,
                        "encoding": "base64",
                        "size": size,
                        "content": "",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ) + 4 * ((size + 2) // 3)
            if minimum > SNAPSHOT_RESPONSE_MAX_BYTES:
                limitations.append(f"L1 응답 크기 상한으로 보조 원문을 읽지 않았습니다: {path}")
                continue
        try:
            value = await get(f"/contents/{quote(path, safe='/')}", {"ref": sha})
            if (
                value.get("type") != "file"
                or value.get("path") != path
                or value.get("sha") != blob
                or value.get("encoding") != "base64"
                or not isinstance(value.get("content"), str)
            ):
                raise ValueError("invalid file")
            raw = base64.b64decode(
                str(value["content"]).replace("\n", "").replace("\r", ""), validate=True
            )
            digest = hashlib.sha1(
                f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False
            ).hexdigest()
            if value.get("size") != len(raw) or digest != blob or b"\0" in raw:
                raise ValueError("invalid source")
            text = raw.decode("utf-8")
            if not text.strip():
                continue
            truncated = len(text) > max_file_chars
            if truncated:
                kept: list[str] = []
                for line in text.splitlines(keepends=True):
                    if sum(map(len, kept)) + len(line) > max_file_chars:
                        break
                    kept.append(line)
                text = "".join(kept)
                limitations.append(f"L1 보조 원문 길이 상한 이후는 확인하지 못했습니다: {path}")
            if text:
                files.append(RepoSupportingFile(path, text, truncated))
        except GithubApiError as error:
            if error.error_code in {"rate_limited", "token_invalid"}:
                raise
            limitations.append(f"L1 보조 원문을 읽지 못했습니다: {path}")
        except (ValueError, UnicodeError, binascii.Error):
            limitations.append(f"L1에서 지원 텍스트로 확인하지 못했습니다: {path}")
    return tuple(structure), tuple(files), tuple(dict.fromkeys(limitations))
