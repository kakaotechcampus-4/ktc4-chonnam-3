"""evidence tool 사용 비율 쿼리.

task-17
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TurnEvidence
from app.features.metrics import queries
from tests.features.interview.factories import (
    make_evidence,
    make_interview,
    make_repo,
    make_run,
    make_turn,
    make_user,
)


async def _seed(db: AsyncSession):
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    return await make_interview(db, run, [repo]), repo


async def _link(db: AsyncSession, turn, evidence, usage: str) -> None:
    db.add(TurnEvidence(turn_id=turn.id, evidence_id=evidence.id, usage=usage))
    await db.flush()


async def test_ratio_counts_turns_not_evidences(db: AsyncSession) -> None:
    interview, repo = await _seed(db)
    prep = await make_evidence(db, interview, repo)
    tool_a = await make_evidence(db, interview, repo, tool_name="read_file")
    tool_b = await make_evidence(db, interview, repo, tool_name="get_commit")
    t1 = await make_turn(db, interview, 1)  # 사전 분석 근거만
    t2 = await make_turn(db, interview, 2)  # Tool 근거 2건 + 사전 근거 1건 → 1턴으로 센다
    t3 = await make_turn(db, interview, 3)  # 근거 없음 → 분모 제외
    await _link(db, t1, prep, "question_basis")
    await _link(db, t2, tool_a, "question_basis")
    await _link(db, t2, tool_b, "evaluation_basis")
    await _link(db, t2, prep, "evaluation_basis")
    assert t3.id is not None

    usage = await queries.get_evidence_tool_usage(db)

    assert (usage.turns_with_evidence, usage.turns_with_tool) == (2, 1)
    assert usage.ratio == pytest.approx(0.5)


async def test_ratio_none_without_data(db: AsyncSession) -> None:
    interview, _ = await _seed(db)
    await make_turn(db, interview, 1)

    usage = await queries.get_evidence_tool_usage(db)

    assert (usage.turns_with_evidence, usage.turns_with_tool) == (0, 0)
    assert usage.ratio is None


async def test_ratio_period_filter(db: AsyncSession) -> None:
    interview, repo = await _seed(db)
    tool = await make_evidence(db, interview, repo, tool_name="read_file")
    prep = await make_evidence(db, interview, repo)
    now = datetime.now(UTC)
    old = await make_turn(db, interview, 1)
    old.created_at = now - timedelta(days=10)
    recent = await make_turn(db, interview, 2)
    await _link(db, old, tool, "question_basis")
    await _link(db, recent, prep, "question_basis")

    since = now - timedelta(days=1)
    recent_usage = await queries.get_evidence_tool_usage(db, since=since)
    old_usage = await queries.get_evidence_tool_usage(db, until=since)

    assert recent_usage.ratio == 0.0
    assert old_usage.ratio == 1.0
