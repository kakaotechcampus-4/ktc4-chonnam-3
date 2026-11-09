"""큰 파일은 고정 ref에서 제한된 원문 줄까지만 읽고 미확인을 보존한다."""

import hashlib

import httpx
import pytest

from app.integrations.github.evidence import EvidenceReader, EvidenceReadError


async def test_raw_prefix_reads_complete_lines_without_following_download_url():
    text = ("한글 line\n" * 300).encode()
    sha = "a" * 40
    blob = hashlib.sha1(f"blob {len(text)}\0".encode() + text).hexdigest()

    def handler(request):
        assert request.url.host == "api.github.com"
        assert request.url.params["ref"] == sha
        assert request.headers["accept"] == "application/vnd.github.raw+json"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=text)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"Authorization": "must-not-inherit"}
    ) as http:
        reader = EvidenceReader(
            http,
            "o/r",
            max_requests=1,
            max_response_bytes=100,
            max_total_bytes=100,
            timeout_seconds=1,
        )
        actual, complete = await reader.file_text_prefix(
            "nested/x.lang", sha, blob, max_bytes=100, expected_size=len(text)
        )
    assert actual.encode() == text[: len(actual.encode())]
    assert actual.endswith("\n")
    assert len(actual.encode()) <= 100
    assert not complete
    assert reader.requests_left == 0


async def test_full_raw_read_rejects_blob_mismatch():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"text\n"))
    ) as http:
        reader = EvidenceReader(
            http,
            "o/r",
            max_requests=1,
            max_response_bytes=100,
            max_total_bytes=100,
            timeout_seconds=1,
        )
        with pytest.raises(EvidenceReadError, match="github_invalid_response"):
            await reader.file_text_prefix(
                "x.py", "a" * 40, "b" * 40, max_bytes=100, expected_size=5
            )
