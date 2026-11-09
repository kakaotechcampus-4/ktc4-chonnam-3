"""선택하지 않은 외부 PDF 전송과 일시 실패의 장기 캐시를 방지한다."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.db.models import JobPosting, User
from app.features.analysis import posting_service
from app.features.documents.service import preview_document
from tests.integrations.test_extract import build_pdf


@pytest.mark.asyncio
async def test_native_pdf_is_not_sent_to_vision_by_default():
    owner = User(id=uuid4(), name="fixture", status="active")
    db = AsyncMock()
    db.get.return_value = owner
    db.add = lambda row: setattr(row, "id", uuid4())
    vision = SimpleNamespace(
        extract=AsyncMock(side_effect=AssertionError("unnecessary external call"))
    )
    upload = UploadFile(file=BytesIO(build_pdf("Native source")), filename="portfolio.pdf")
    await preview_document(
        db, owner, upload, max_file_bytes=100000, max_text_chars=10000, vision_client=vision
    )
    vision.extract.assert_not_awaited()
    assert Settings(_env_file=None).vision_pdf_layout is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,age,reusable",
    [("failed", 61, False), ("partial", 61, False), ("failed", 30, True), ("succeeded", 61, True)],
)
async def test_transient_image_extraction_uses_short_retry_window(
    monkeypatch, status, age, reusable
):
    now = datetime.now(UTC)
    posting = JobPosting(
        fetched_at=now - timedelta(seconds=age),
        raw_payload={"_image_extraction": {"status": status, "attempts": []}},
    )
    monkeypatch.setattr(posting_service, "get_posting_requirements", AsyncMock(return_value=[]))
    assert (
        await posting_service._reusable_success(AsyncMock(), posting, now, timedelta(days=7))
        is reusable
    )


@pytest.mark.parametrize("status", ["failed", "partial"])
def test_partial_image_collection_is_retried_even_when_remaining_jd_extraction_succeeds(status):
    now = datetime.now(UTC)
    snapshot = {
        "_image_extraction": {"status": "succeeded"},
        "source_metadata": {"image_processing": {"status": status}},
    }
    posting = JobPosting(fetched_at=now - timedelta(seconds=61), raw_payload=snapshot)
    assert posting_service._fresh(posting, now, timedelta(days=7)) is False
    complete = {**snapshot, "source_metadata": {"image_processing": {"status": "succeeded"}}}
    assert posting_service._image_health(snapshot) != posting_service._image_health(complete)
