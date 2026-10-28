"""report/queries.py — 소유권, 리포트 조회, 답변 완료 턴 수, 점수 순서.

task-16
"""

import uuid

import pytest

from app.features.report import queries

from ..interview.factories import make_interview, make_repo, make_run, make_turn, make_user
from .factories import make_disagreement, make_report, seed_criteria


@pytest.fixture
async def setup(db):
    user = await make_user(db)
    run = await make_run(db, user)
    repos = [await make_repo(db, run), await make_repo(db, run)]
    interview = await make_interview(db, run, repos, status="completed")
    await db.commit()
    return user, interview, repos


async def test_get_owned_interview_rejects_other_user(db, setup) -> None:
    user, interview, _ = setup
    assert await queries.get_owned_interview(db, user_id=user.id, interview_id=interview.id)
    other = await make_user(db)
    assert (
        await queries.get_owned_interview(db, user_id=other.id, interview_id=interview.id) is None
    )
    assert await queries.get_owned_interview(db, user_id=user.id, interview_id=uuid.uuid4()) is None


async def test_count_answered_turns_ignores_asked(db, setup) -> None:
    _, interview, _ = setup
    await make_turn(db, interview, 1, answered=True)
    await make_turn(db, interview, 2)
    await db.commit()
    assert await queries.count_answered_turns(db, interview_id=interview.id) == 1


async def test_get_report_none_before_generation(db, setup) -> None:
    _, interview, _ = setup
    assert await queries.get_report(db, interview_id=interview.id) is None
    report = await make_report(db, interview)
    assert (await queries.get_report(db, interview_id=interview.id)).id == report.id


async def test_list_scores_uses_label_and_criteria_order(db, setup) -> None:
    _, interview, _ = setup
    await seed_criteria(db)
    report = await make_report(db, interview)
    scores = await queries.list_scores(db, report_id=report.id)
    assert [key for key, _, _ in scores][:2] == ["project_understanding", "technical_reasoning"]
    assert scores[0] == ("project_understanding", "프로젝트 이해도", 80.0)
    assert len(scores) == 6


async def test_list_disagreed_personas(db, setup) -> None:
    _, interview, _ = setup
    report = await make_report(db, interview)
    assert await queries.list_disagreed_personas(db, report_id=report.id) == set()
    await make_disagreement(db, report, "tech_lead")
    assert await queries.list_disagreed_personas(db, report_id=report.id) == {"tech_lead"}


async def test_list_repository_names_in_selection_order(db, setup) -> None:
    _, interview, repos = setup
    assert await queries.list_repository_names(db, interview_id=interview.id) == [
        repos[0].name,
        repos[1].name,
    ]


async def test_list_turns_ordered(db, setup) -> None:
    _, interview, _ = setup
    await make_turn(db, interview, 2)
    await make_turn(db, interview, 1, answered=True)
    await db.commit()
    turns = await queries.list_turns(db, interview_id=interview.id)
    assert [t.turn_no for t in turns] == [1, 2]
