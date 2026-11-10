"""실제 PostgreSQL 저장 실패의 재전달과 확정 생성 결과 재사용을 검증한다."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.db.models import InterviewReport, InterviewTurn, ProfileRefreshRequest, UserProfileSummary
from app.features.profile import refresh_outbox as outbox
from app.features.profile import service
from app.workers.tasks import profile_summary as worker
from tests.features.profile.fakes import ROLE, read_summary
from tests.features.profile.test_profile_outbox_worker import prepare


async def raise_database_error(db, sqlstate):
    assert sqlstate in {"40001", "40P01", "08006", "57P01", "23505", "42601", "08P01"}
    with pytest.raises(DBAPIError) as raised:
        await db.execute(
            text(
                "DO $$ BEGIN RAISE EXCEPTION 'profile retry fixture' "
                f"USING ERRCODE = '{sqlstate}'; END $$"
            )
        )
    assert raised.value.orig.sqlstate == sqlstate
    raise raised.value


@pytest.mark.parametrize("sqlstate", ["40001", "40P01", "08006", "57P01"])
@pytest.mark.parametrize("change_input", [False, True])
async def test_transient_save_retries_preserved_generation_for_matching_input(
    app, db, world, monkeypatch, sqlstate, change_input
):
    user, rid, ctx, generator = await prepare(app, db, world, monkeypatch)
    assert await outbox.dispatch(app.state.session_factory, app.state.redis, rid)
    original_save = service.queries.save_summary

    async def fail_after_insert(session, **kwargs):
        async with app.state.session_factory() as independent:
            row = await independent.get(ProfileRefreshRequest, rid)
            assert row.status == "running" and row.dispatch_attempts == 1
            assert row.generated_result["role_summary"] == ROLE
        await original_save(session, **kwargs)
        assert await session.scalar(select(func.count()).select_from(UserProfileSummary)) == 1
        await raise_database_error(session, sqlstate)

    monkeypatch.setattr(service.queries, "save_summary", fail_after_insert)
    await worker.profile_summary(ctx, str(user.id), str(rid), 1)
    monkeypatch.setattr(service.queries, "save_summary", original_save)
    row = await db.get(ProfileRefreshRequest, rid, populate_existing=True)
    assert row.status == "pending" and row.last_error == "profile_database_unavailable"
    assert row.generated_result["role_summary"] == ROLE
    assert row.owner_token is None and row.lease_expires_at is None
    assert len(generator.calls) == 1 and await read_summary(db, user) is None
    assert await db.scalar(select(func.count()).select_from(InterviewReport)) == 1
    if change_input:
        (await db.scalar(select(InterviewTurn))).answer_text = "설정 검증과 테스트를 구현했습니다."
        await db.commit()
    assert (
        await outbox.recover(app.state.session_factory, app.state.redis, now=row.next_attempt_at)
        == 1
    )
    await worker.profile_summary(ctx, str(user.id), str(rid), 2)
    await db.refresh(row)
    assert row.status == "succeeded" and row.generated_result is None
    assert len(generator.calls) == (2 if change_input else 1)
    assert (await read_summary(db, user)).role_summary == ROLE


@pytest.mark.parametrize("boundary", ["last_attempt", "expired", "stale_owner", "defer_failure"])
async def test_transient_save_respects_delivery_boundaries(app, db, world, monkeypatch, boundary):
    user, rid, ctx, generator = await prepare(app, db, world, monkeypatch)
    row = await db.get(ProfileRefreshRequest, rid)
    if boundary == "last_attempt":
        row.dispatch_attempts = outbox.MAX_DISPATCH_ATTEMPTS - 1
        await db.commit()
    attempt = row.dispatch_attempts + 1
    assert await outbox.dispatch(app.state.session_factory, app.state.redis, rid)
    original_save, original_finish = service.queries.save_summary, outbox.finish
    replacement = uuid4()

    async def fail_after_insert(session, **kwargs):
        await original_save(session, **kwargs)
        if boundary in {"expired", "stale_owner"}:
            async with app.state.session_factory.begin() as independent:
                request = await independent.get(ProfileRefreshRequest, rid, with_for_update=True)
                if boundary == "expired":
                    request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                else:
                    request.owner_token = replacement
        await raise_database_error(session, "40001")

    async def unavailable_finish(*args, **kwargs):
        async with app.state.session_factory.begin() as independent:
            await raise_database_error(independent, "08006")

    monkeypatch.setattr(service.queries, "save_summary", fail_after_insert)
    if boundary == "defer_failure":
        monkeypatch.setattr(outbox, "finish", unavailable_finish)
    await worker.profile_summary(ctx, str(user.id), str(rid), attempt)
    monkeypatch.setattr(service.queries, "save_summary", original_save)
    monkeypatch.setattr(outbox, "finish", original_finish)
    await db.refresh(row)
    assert len(generator.calls) == 1 and await read_summary(db, user) is None
    if boundary in {"last_attempt", "expired"}:
        assert row.status == "failed" and row.generated_result is None
        assert await outbox.recover(app.state.session_factory, app.state.redis) == 0
    else:
        assert row.status == "running" and row.generated_result["role_summary"] == ROLE
        assert row.owner_token is not None and row.lease_expires_at is not None
        if boundary == "stale_owner":
            assert row.owner_token == replacement
        assert (
            await outbox.recover(
                app.state.session_factory,
                app.state.redis,
                now=row.lease_expires_at + timedelta(seconds=1),
            )
            == 1
        )
        await worker.profile_summary(ctx, str(user.id), str(rid), attempt + 1)
        await db.refresh(row)
        assert row.status == "succeeded" and len(generator.calls) == 1


@pytest.mark.parametrize("fault", ["23505", "42601", "08P01", "uncoded_operational"])
async def test_permanent_database_error_does_not_redeliver(app, db, world, monkeypatch, fault):
    user, rid, ctx, generator = await prepare(app, db, world, monkeypatch)
    assert await outbox.dispatch(app.state.session_factory, app.state.redis, rid)
    original_save = service.queries.save_summary

    async def fail_after_insert(session, **kwargs):
        await original_save(session, **kwargs)
        if fault == "uncoded_operational":
            raise OperationalError("fixture", {}, OSError("40001 connection reset"))
        await raise_database_error(session, fault)

    monkeypatch.setattr(service.queries, "save_summary", fail_after_insert)
    await worker.profile_summary(ctx, str(user.id), str(rid), 1)
    row = await db.get(ProfileRefreshRequest, rid, populate_existing=True)
    assert row.status == "failed" and row.generated_result is None
    assert len(generator.calls) == 1 and await read_summary(db, user) is None
    assert await outbox.recover(app.state.session_factory, app.state.redis) == 0


async def test_invalidated_connection_retries_without_a_sqlstate(app, db, world, monkeypatch):
    user, rid, ctx, generator = await prepare(app, db, world, monkeypatch)
    assert await outbox.dispatch(app.state.session_factory, app.state.redis, rid)

    async def unavailable(*args, **kwargs):
        raise DBAPIError("fixture", {}, OSError("fixture"), connection_invalidated=True)

    monkeypatch.setattr(service.queries, "save_summary", unavailable)
    await worker.profile_summary(ctx, str(user.id), str(rid), 1)
    row = await db.get(ProfileRefreshRequest, rid, populate_existing=True)
    assert row.status == "pending" and row.generated_result["role_summary"] == ROLE
    assert len(generator.calls) == 1 and await read_summary(db, user) is None
