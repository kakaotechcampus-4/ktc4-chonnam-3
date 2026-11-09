"""직접 생성한 GitHub 요청도 필수 앱 식별 헤더를 명시한다."""

import hashlib

import httpx
import pytest

from app.integrations.github.client import GithubClient
from app.integrations.github.evidence import EvidenceReader


@pytest.mark.parametrize("operation", ["snapshot", "evidence_json", "evidence_raw"])
async def test_direct_github_requests_send_explicit_application_user_agent(operation):
    content = b"code\n"
    blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()

    def handler(request):
        assert request.headers.get("User-Agent") == "DEVON"
        if operation == "evidence_raw":
            return httpx.Response(200, content=content)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "client-default"}
    ) as http:
        if operation == "snapshot":
            await GithubClient("fixture", client=http)._snapshot_json("/repos/o/r", None)
        else:
            reader = EvidenceReader(
                http,
                "o/r",
                max_requests=1,
                max_response_bytes=100,
                max_total_bytes=100,
                timeout_seconds=1,
            )
            if operation == "evidence_json":
                await reader.get("")
            else:
                await reader.file_text_prefix(
                    "x.py", "a" * 40, blob, max_bytes=100, expected_size=len(content)
                )
