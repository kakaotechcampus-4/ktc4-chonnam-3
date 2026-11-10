"""조회 잠금과 생성 요청 종결은 실제 PostgreSQL에서 검사한다. 모델은 호출하지 않는다."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn
from app.db.models.report import ReportGenerationRequest
from app.features.report import service
from app.shared.enums import Reason

from .factories import make_report
from .fakes import LLM, FakeGenerator


async def _get(app, interview):
    async with app.state.session_factory() as db:
        return await service.get_report(
            db, app.state.redis, user_id=interview.user_id, interview_id=interview.id
        )


async def test_ready_report_readers_can_hold_the_same_snapshot_concurrently(
    app, db, ctx, monkeypatch
):
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()
    original = service._build_report
    both_reading = asyncio.Event()
    entered = 0

    async def read_snapshot(*args):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_reading.set()
        await asyncio.wait_for(both_reading.wait(), 5)
        return await original(*args)

    monkeypatch.setattr(service, "_build_report", read_snapshot)
    first, second = await asyncio.wait_for(
        asyncio.gather(_get(app, interview), _get(app, interview)), 10
    )
    assert entered == 2
    assert first.revision == second.revision == 1
    assert first.scores == second.scores


async def test_generation_poll_uses_database_request_without_redis_await(app, db, ctx, monkeypatch):
    interview, _ = ctx
    db.add(
        ReportGenerationRequest(
            interview_session_id=interview.id,
            mode="retry",
            status="running",
            expected_revision=0,
            requested_by="review-test",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    await db.commit()

    async def no_redis(*args):
        raise AssertionError("active generation polling must not query Redis")

    monkeypatch.setattr(service, "_has_failure_history", no_redis)
    response = await _get(app, interview)
    assert response.status == "generating"


async def test_failure_history_lookup_does_not_hold_interview_row_lock(app, db, ctx, monkeypatch):
    interview, _ = ctx
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def delayed_failure(*args):
        waiting.set()
        await asyncio.wait_for(release.wait(), 5)
        return True

    monkeypatch.setattr(service, "_has_failure_history", delayed_failure)
    request = asyncio.create_task(_get(app, interview))
    await asyncio.wait_for(waiting.wait(), 5)
    try:
        async with app.state.session_factory.begin() as other:
            locked = await other.scalar(
                select(InterviewSession)
                .where(InterviewSession.id == interview.id)
                .with_for_update(nowait=True)
            )
            assert locked is not None
    finally:
        release.set()
        with pytest.raises(AppError) as error:
            await request
        assert error.value.reason == Reason.REPORT_UNAVAILABLE


@pytest.mark.parametrize("existing", [True, False])
async def test_no_model_early_return_closes_its_running_request(app, db, ctx, existing):
    interview, _ = ctx
    if existing:
        await make_report(db, interview)
    else:
        await db.execute(
            delete(InterviewTurn).where(InterviewTurn.interview_session_id == interview.id)
        )
    request = ReportGenerationRequest(
        interview_session_id=interview.id,
        mode="initial",
        status="running",
        expected_revision=0,
        requested_by="review-test",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(request)
    await db.commit()
    generator = FakeGenerator()
    result = await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=generator,
        generation_request_id=request.id,
    )
    await db.refresh(request)
    assert result == ("exists" if existing else "skipped")
    assert request.status == "stale"
    assert request.error_code == ("report_already_exists" if existing else "no_answered_turns")
    assert generator.calls == []
