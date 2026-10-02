"""Evidence 전용 제한 조회. 주입 client의 인증·쿠키·redirect 설정을 상속하지 않는다."""

import base64
import binascii
import hashlib
import json
import re
from urllib.parse import quote

import httpx
from pydantic import SecretStr


class EvidenceReadError(Exception):
    """외부 원문이나 비밀값 대신 고정된 오류 코드만 전달한다."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise EvidenceReadError("github_invalid_response")
    return value


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


class EvidenceReader:
    """한 read_files 실행의 HTTP·응답 바이트 예산과 부모 tree 캐시를 관리한다."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        full_name: str,
        *,
        max_requests: int,
        max_response_bytes: int,
        max_total_bytes: int,
        timeout_seconds: float,
    ) -> None:
        self.http = http_client
        self.base = f"https://api.github.com/repos/{full_name}"
        self.requests_left = max_requests
        self.response_limit = max_response_bytes
        self.bytes_left = max_total_bytes
        self.timeout = timeout_seconds
        self.trees: dict[str, list[object]] = {}

    async def get(
        self, suffix: str, *, ref: str | None = None, token: SecretStr | None = None
    ) -> dict[str, object] | None:
        if self.requests_left == 0 or self.bytes_left == 0:
            raise EvidenceReadError("evidence_budget_exhausted")
        self.requests_left -= 1
        headers = {"Accept": "application/vnd.github+json", "Accept-Encoding": "identity"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        # Request를 직접 만들어 client의 default auth·cookie·base_url을 배제한다.
        request = httpx.Request(
            "GET",
            self.base + suffix,
            params={"ref": ref} if ref is not None else None,
            headers=headers,
            extensions={"timeout": httpx.Timeout(self.timeout).as_dict()},
        )
        try:
            response = await self.http.send(request, stream=True, auth=None, follow_redirects=False)
            try:
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise EvidenceReadError(f"github_http_{response.status_code}")
                # 압축 폭탄을 피한다. 오류 본문·download_url은 읽거나 따라가지 않는다.
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise EvidenceReadError("github_invalid_response")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    self.bytes_left -= len(chunk)
                    if self.bytes_left < 0 or len(body) + len(chunk) > self.response_limit:
                        raise EvidenceReadError("evidence_byte_limit")
                    body.extend(chunk)
            finally:
                await response.aclose()
        except httpx.TimeoutException:
            raise EvidenceReadError("github_timeout") from None
        except httpx.HTTPError:
            raise EvidenceReadError("github_transport_error") from None
        try:
            payload: object = json.loads(body, object_pairs_hook=_object)
        except (ValueError, UnicodeError, RecursionError):
            raise EvidenceReadError("github_invalid_response") from None
        if not isinstance(payload, dict):
            raise EvidenceReadError("github_invalid_response")
        return payload

    async def root_tree(self, commit_sha: str) -> str | None:
        commit = await self.get(f"/git/commits/{commit_sha}")
        if commit is None:
            return None
        tree = commit.get("tree")
        if commit.get("sha") != commit_sha or not isinstance(tree, dict):
            raise EvidenceReadError("github_invalid_response")
        return _sha(tree.get("sha"))

    async def regular_blob(self, root_sha: str, path: str) -> str | None:
        """승인 경로의 부모만 비재귀 조회한다. symlink·submodule·디렉터리는 읽지 않는다."""
        current = root_sha
        parts = path.split("/")
        for index, part in enumerate(parts):
            if current not in self.trees:
                tree = await self.get(f"/git/trees/{current}")
                if tree is None:
                    raise EvidenceReadError("github_tree_unavailable")
                entries = tree.get("tree")
                if (
                    tree.get("sha") != current
                    or tree.get("truncated") is not False
                    or not isinstance(entries, list)
                ):
                    raise EvidenceReadError("github_invalid_response")
                if any(
                    not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                    for entry in entries
                ):
                    raise EvidenceReadError("github_invalid_response")
                self.trees[current] = entries
            matches = [
                entry
                for entry in self.trees[current]
                if isinstance(entry, dict) and entry.get("path") == part
            ]
            if not matches:
                return None
            if len(matches) != 1:
                raise EvidenceReadError("github_invalid_response")
            entry = matches[0]
            final = index == len(parts) - 1
            expected_modes = {"100644", "100755"} if final else {"040000"}
            if not isinstance(entry.get("mode"), str):
                raise EvidenceReadError("github_invalid_response")
            if entry.get("mode") not in expected_modes or entry.get("type") != (
                "blob" if final else "tree"
            ):
                raise EvidenceReadError("evidence_not_regular_file")
            current = _sha(entry.get("sha"))
        return current

    async def file_text(self, path: str, commit_sha: str, blob_sha: str) -> str:
        payload = await self.get(f"/contents/{quote(path, safe='/')}", ref=commit_sha)
        if payload is None:
            raise EvidenceReadError("github_file_unavailable")
        encoded = payload.get("content")
        if (
            payload.get("type") != "file"
            or payload.get("path") != path
            or payload.get("sha") != blob_sha
            or payload.get("encoding") != "base64"
            or not isinstance(encoded, str)
            or type(payload.get("size")) is not int
            or "submodule_git_url" in payload
            or "target" in payload
        ):
            raise EvidenceReadError("github_invalid_response")
        try:
            content = base64.b64decode(encoded.replace("\n", "").replace("\r", ""), validate=True)
            # tree에서 확인한 blob과 내용의 일치를 검증한다. SHA-1은 Git 객체 식별 규칙이다.
            actual = hashlib.sha1(
                f"blob {len(content)}\0".encode("ascii") + content, usedforsecurity=False
            ).hexdigest()
            if payload["size"] != len(content) or actual != blob_sha:
                raise EvidenceReadError("github_invalid_response")
            text = content.decode("utf-8")
        except (ValueError, UnicodeError, binascii.Error):
            raise EvidenceReadError("github_invalid_response") from None
        if "\0" in text:
            raise EvidenceReadError("evidence_not_text")
        return text
