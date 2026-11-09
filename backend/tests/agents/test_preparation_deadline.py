"""단계별 HTTP 제한과 별개로 준비 전체를 유한하게 종료한다."""

import asyncio
from uuid import uuid4

import pytest

from app.features.interview import prepare, prepare_lease


def test_final_preparation_admission_includes_documents_comparison_and_retry_wait():
    prepare_lease.validate_timeout(30, 50, deep_seconds=120)
    with pytest.raises(prepare_lease.PreparationTimeoutError):
        prepare_lease.validate_timeout(30, 50, deep_seconds=250)
    assert prepare_lease.PREPARATION_DEADLINE_SECONDS < prepare_lease.JOB_TIMEOUT_SECONDS


async def test_overall_deadline_cancels_inner_preparation(monkeypatch):
    canceled = []

    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            canceled.append(True)

    monkeypatch.setattr(prepare_lease, "PREPARATION_DEADLINE_SECONDS", 0.02)
    monkeypatch.setattr(prepare, "_prepare_interview", blocked)
    assert (
        await prepare.prepare_interview(
            None, user_id=uuid4(), interview_id=uuid4(), settings=None, http_client=None
        )
        is False
    )
    assert canceled == [True]
