"""repo_recommended 이벤트 연결: 추천 결과 저장 시 run당 1건. task-17"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.metric import Event
from app.features.analysis.candidates import prepare_candidates
from app.features.analysis.matching import refresh_matches
from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import names
from tests.features.analysis.test_matching import seed_run
from tests.features.interview.factories import make_repo, make_run, make_user


async def _payloads(db: AsyncSession) -> list[dict[str, object]]:
    await db.rollback()
    return list(
        await db.scalars(select(Event.payload).where(Event.event_name == "repo_recommended"))
    )


async def test_recorded_when_matches_saved_with_counts(db_session: AsyncSession) -> None:
    run, _ = await seed_run(db_session)

    await refresh_matches(db_session, run.id)
    await db_session.commit()

    assert await _payloads(db_session) == [{"candidateCount": 8, "recommendedCount": 5}]


async def test_recorded_once_per_run_across_repeated_refresh(db_session: AsyncSession) -> None:
    run, _ = await seed_run(db_session)

    for _ in range(3):  # 페이지마다 refresh_matches 가 다시 불린다
        await refresh_matches(db_session, run.id)
        await db_session.commit()

    assert await names(db_session, "repo_recommended") == ["repo_recommended"]


async def test_recorded_with_zero_recommendations(db_session: AsyncSession) -> None:
    run, candidates = await seed_run(db_session, count=2)
    for candidate in candidates:  # 모든 후보가 제외된 결과
        candidate.filter_status = "excluded"
    await db_session.commit()

    await refresh_matches(db_session, run.id)
    await db_session.commit()

    assert await _payloads(db_session) == [{"candidateCount": 0, "recommendedCount": 0}]


async def test_not_recorded_when_only_candidates_are_prepared(db) -> None:
    run = await make_run(db, await make_user(db), status="running")
    await make_repo(db, run, in_run=False)

    rows = await prepare_candidates(db, run.id, min_size_kb=0)
    await db.commit()

    assert len(rows) == 1
    assert await names(db) == []


async def test_event_failure_does_not_block_match_save(
    db_session: AsyncSession, broken_events
) -> None:
    run, _ = await seed_run(db_session)

    rows = await refresh_matches(db_session, run.id)
    await db_session.commit()

    assert sum(row.is_recommended for row in rows) == 5
    assert await names(db_session) == []


async def test_event_lookup_lock_timeout_does_not_rollback_matches(
    db_session: AsyncSession, session_factory
) -> None:
    run, _ = await seed_run(db_session)
    async with session_factory() as blocker:
        await blocker.execute(text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE"))
        try:
            await db_session.execute(text("SET LOCAL lock_timeout = '150ms'"))
            rows = await refresh_matches(db_session, run.id)
            await db_session.commit()
        finally:
            await blocker.rollback()

    assert len(rows) == 8
    assert sum(row.is_recommended for row in rows) == 5
    # 선택 지표의 조회 실패도 업무 결과와 분리하고 성공 이벤트를 지어내지 않는다.
    assert await names(db_session) == []
