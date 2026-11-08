"""Evidence 전용 제한 조회. 주입 client의 인증·쿠키·redirect 설정을 상속하지 않는다."""

import base64
import binascii
import hashlib
import json
import re
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.integrations.github.base import GITHUB_USER_AGENT


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
        public_app_auth: tuple[str, SecretStr] | None = None,
    ) -> None:
        if public_app_auth is not None:
            if (
                type(public_app_auth) is not tuple
                or len(public_app_auth) != 2
                or type(public_app_auth[0]) is not str
                or not isinstance(public_app_auth[1], SecretStr)
            ):
                raise EvidenceReadError("github_credentials_invalid")
            client_id, client_secret = public_app_auth
            if ":" in client_id or any(
                not value
                or value != value.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in value)
                for value in (client_id, client_secret.get_secret_value())
            ):
                raise EvidenceReadError("github_credentials_invalid")
        self.http = http_client
        self.base = f"https://api.github.com/repos/{full_name}"
        self.requests_left = max_requests
        self.response_limit = max_response_bytes
        self.bytes_left = max_total_bytes
        self.timeout = timeout_seconds
        self.trees: dict[str, list[object]] = {}
        self.blob_sizes: dict[str, int] = {}
        self._public_app_auth = public_app_auth

    async def get(
        self,
        suffix: str,
        *,
        ref: str | None = None,
        token: SecretStr | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object] | None:
        if self.requests_left == 0 or self.bytes_left == 0:
            raise EvidenceReadError("evidence_budget_exhausted")
        read_limit = (
            self.response_limit if max_bytes is None else min(self.response_limit, max_bytes)
        )
        if read_limit <= 0:
            raise EvidenceReadError("evidence_budget_exhausted")
        self.requests_left -= 1
        headers = {
            "Accept": "application/vnd.github+json",
            "Accept-Encoding": "identity",
            "User-Agent": GITHUB_USER_AGENT,
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        elif self._public_app_auth is not None:
            # 공개 데이터용 OAuth 앱 인증만 명시하며 사용자 token의 조회 범위를 넓히지 않는다.
            client_id, secret = self._public_app_auth
            basic = base64.b64encode(f"{client_id}:{secret.get_secret_value()}".encode()).decode()
            headers["Authorization"] = f"Basic {basic}"
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
                declared = response.headers.get("Content-Length", "")
                if max_bytes is not None and declared.isdecimal() and int(declared) > read_limit:
                    raise EvidenceReadError("evidence_byte_limit")
                body = bytearray()
                async for chunk in response.aiter_bytes(
                    chunk_size=read_limit if max_bytes is not None else None
                ):
                    self.bytes_left -= len(chunk)
                    if self.bytes_left < 0 or len(body) + len(chunk) > read_limit:
                        raise EvidenceReadError("evidence_byte_limit")
                    body.extend(chunk)
                    # 구조 응답은 경계에서 보수적으로 중단해 원문 몫을 읽지 않는다.
                    if max_bytes is not None and len(body) == read_limit:
                        raise EvidenceReadError("evidence_byte_limit")
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
            if final and entry.get("mode") == "040000" and entry.get("type") == "tree":
                # 디렉터리 tree는 요청하지 않는다. 호출자가 경로별 분석 한계로 구분한다.
                raise EvidenceReadError("evidence_directory")
            if entry.get("mode") not in expected_modes or entry.get("type") != (
                "blob" if final else "tree"
            ):
                raise EvidenceReadError("evidence_not_regular_file")
            if final and type(entry.get("size")) is int and entry["size"] >= 0:
                self.blob_sizes[str(entry["sha"])] = entry["size"]
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

    async def file_text_prefix(
        self, path: str, commit_sha: str, blob_sha: str, *, max_bytes: int, expected_size: int
    ) -> tuple[str, bool]:
        """큰 파일의 실제 원문 prefix만 읽는다. 미완료 본문은 완성된 줄까지만 반환한다.

        GitHub Contents의 raw media type을 고정 ref에 요청하며 download_url은 따라가지 않는다.
        전체 읽기를 마친 경우에만 Git blob hash를 검증하고, 부분 읽기는 명시적으로 구분한다.
        """
        if self.requests_left <= 0 or self.bytes_left <= 0 or max_bytes <= 0:
            raise EvidenceReadError("evidence_budget_exhausted")
        self.requests_left -= 1
        limit = min(max_bytes, self.response_limit, self.bytes_left)
        headers = {
            "Accept": "application/vnd.github.raw+json",
            "Accept-Encoding": "identity",
            "User-Agent": GITHUB_USER_AGENT,
        }
        if self._public_app_auth is not None:
            client_id, secret = self._public_app_auth
            basic = base64.b64encode(f"{client_id}:{secret.get_secret_value()}".encode()).decode()
            headers["Authorization"] = f"Basic {basic}"
        request = httpx.Request(
            "GET",
            self.base + f"/contents/{quote(path, safe='/')}",
            params={"ref": commit_sha},
            headers=headers,
            extensions={"timeout": httpx.Timeout(self.timeout).as_dict()},
        )
        body = bytearray()
        complete = True
        try:
            response = await self.http.send(request, stream=True, auth=None, follow_redirects=False)
            try:
                if response.status_code != 200:
                    raise EvidenceReadError(f"github_http_{response.status_code}")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise EvidenceReadError("github_invalid_response")
                async for part in response.aiter_bytes(chunk_size=limit):
                    self.bytes_left -= len(part)
                    body.extend(part[: limit - len(body)])
                    if len(body) == limit and expected_size > limit:
                        complete = False
                        break
                    if len(body) >= limit:
                        complete = False
                        break
            finally:
                await response.aclose()
        except httpx.TimeoutException:
            raise EvidenceReadError("github_timeout") from None
        except httpx.HTTPError:
            raise EvidenceReadError("github_transport_error") from None
        raw = bytes(body)
        if len(raw) == expected_size:
            # EOF 직전 상한과 일치해도 Git 객체 전체 hash로 동일성을 확인할 수 있다.
            complete = True
        if complete:
            digest = hashlib.sha1(
                f"blob {len(raw)}\0".encode("ascii") + raw, usedforsecurity=False
            ).hexdigest()
            if len(raw) != expected_size or digest != blob_sha:
                raise EvidenceReadError("github_invalid_response")
        elif b"\n" in raw:
            raw = raw[: raw.rfind(b"\n") + 1]
        else:
            raw = b""
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise EvidenceReadError("evidence_not_text") from None
        if "\0" in text:
            raise EvidenceReadError("evidence_not_text")
        return text, complete
