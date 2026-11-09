"""정지·탈퇴한 사용자의 대기 작업과 캐시 재사용은 모델·저장을 실행하지 않는다."""

import asyncio

import pytest
from sqlalchemy import update

from app.db.models import ProfileRefreshRequest, User
from app.features.profile import queries, refresh_outbox
from app.workers.tasks import profile_summary as worker

from ..interview.factories import make_repo
from .fakes import FakeGenerator, completed_interview, read_summary, refresh_summary
from .test_profile_outbox_worker import prepare


def snapshot(summary):
    if summary is None:
        return None
    return (
        summary.role_summary,
        summary.generated_at,
        summary.input_fingerprint,
        summary.languages,
        summary.project_types,
        summary.based_repo_ids,
        summary.model,
        summary.prompt_version,
    )


@pytest.mark.parametrize("status", ["suspended", "withdrawn"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("entry", ["queued", "legacy", "direct"])
async def test_inactive_user_never_calls_model_or_updates_profile(
    app, db, world, monkeypatch, status, cached, entry
):
    user, rid, ctx, generator = await prepare(app, db, world, monkeypatch)
    if cached:
        await refresh_summary(app, user, FakeGenerator())
    before = snapshot(await read_summary(db, user))
    if entry == "queued":
        assert await refresh_outbox.dispatch(app.state.session_factory, app.state.redis, rid)
    await db.execute(update(User).where(User.id == user.id).values(status=status))
    await db.commit()

    if entry == "queued":
        await worker.profile_summary(ctx, str(user.id), str(rid), 1)
        request = await db.get(ProfileRefreshRequest, rid, populate_existing=True)
        assert request.status == "failed"
        assert request.last_error == "profile_user_inactive"
        assert request.owner_token is None and request.lease_expires_at is None
        assert await refresh_outbox.recover(app.state.session_factory, app.state.redis) == 0
    elif entry == "legacy":
        await worker.profile_summary(ctx, str(user.id))
    else:
        assert await refresh_summary(app, user, generator) == "skipped"
    assert generator.calls == []
    assert snapshot(await read_summary(db, user)) == before


@pytest.mark.parametrize("status", ["suspended", "withdrawn"])
async def test_cache_rechecks_active_user_after_reading_the_reusable_input(
    app, db, world, monkeypatch, status
):
    user, _, _, generator = await prepare(app, db, world, monkeypatch)
    await refresh_summary(app, user, FakeGenerator())
    before = snapshot(await read_summary(db, user))
    await db.commit()
    original = queries.get_summary

    async def deactivate_after_reading(db, *, user_id):
        prior = await original(db, user_id=user_id)
        async with app.state.session_factory.begin() as other:
            await other.execute(update(User).where(User.id == user_id).values(status=status))
        return prior

    monkeypatch.setattr(queries, "get_summary", deactivate_after_reading)
    assert await asyncio.wait_for(refresh_summary(app, user, generator), 10) == "skipped"
    assert generator.calls == []
    assert snapshot(await read_summary(db, user)) == before


@pytest.mark.parametrize("status", ["suspended", "withdrawn"])
async def test_user_deactivated_during_generation_cannot_replace_the_previous_summary(
    app, db, world, monkeypatch, status
):
    user, _, _, _ = await prepare(app, db, world, monkeypatch)
    await refresh_summary(app, user, FakeGenerator())
    before = snapshot(await read_summary(db, user))
    # 새 완료 면접을 추가해 이전 성공본과 다른 실제 입력의 생성 중 철회를 검증한다.
    _, run = world
    await completed_interview(db, run, [await make_repo(db, run, languages={"Go": 1})])

    class DeactivatingGenerator(FakeGenerator):
        async def __call__(self, *args, **kwargs):
            result = await super().__call__(*args, **kwargs)
            async with app.state.session_factory.begin() as other:
                await other.execute(update(User).where(User.id == user.id).values(status=status))
            return result

    generator = DeactivatingGenerator("늦은 결과")
    assert await asyncio.wait_for(refresh_summary(app, user, generator), 10) == "skipped"
    assert len(generator.calls) == 1
    assert snapshot(await read_summary(db, user)) == before
