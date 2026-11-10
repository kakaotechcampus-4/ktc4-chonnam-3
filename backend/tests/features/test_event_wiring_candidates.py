"""후보 준비와 추천 확정 이벤트를 구분한다. task-17"""

from app.features.analysis.candidates import prepare_candidates
from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import names
from tests.features.interview.factories import make_repo, make_run, make_user


async def test_candidate_preparation_does_not_publish_a_recommendation(db):
    user = await make_user(db)
    run = await make_run(db, user, status="running")
    await make_repo(db, run, in_run=False)

    await prepare_candidates(db, run.id, min_size_kb=0)
    await prepare_candidates(db, run.id, min_size_kb=0)
    await db.commit()

    assert await names(db) == []


async def test_candidate_save_does_not_depend_on_event_storage(db, broken_events):
    user = await make_user(db)
    run = await make_run(db, user, status="running")
    await make_repo(db, run, in_run=False)

    rows = await prepare_candidates(db, run.id, min_size_kb=0)

    await db.commit()
    assert len(rows) == 1
    assert await names(db) == []
