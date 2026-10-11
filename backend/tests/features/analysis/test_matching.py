"""추천의 run 전체 상한과 서로 다른 페이지·트랜잭션의 저장 정합성을 검증한다."""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.posting import JdRequirement, JobPosting
from app.db.models.user import User
from app.features.analysis import queries
from app.features.analysis.cards import get_repository_cards
from app.features.analysis.matching import refresh_matches
from app.shared.enums import Reason


async def seed_run(
    session: AsyncSession, count: int = 8
) -> tuple[AnalysisJob, list[AnalysisRepoCandidate]]:
    user = User(name="match tester")
    posting = JobPosting(
        normalized_url=f"https://wanted.co.kr/wd/{uuid.uuid4().int}",
        raw_url="https://wanted.co.kr/wd/1",
        parse_status="succeeded",
        skill_tags=["Python"],
    )
    session.add_all([user, posting])
    await session.flush()
    run = AnalysisJob(
        user_id=user.id, job_type="analysis_run", status="succeeded", job_posting_id=posting.id
    )
    session.add(run)
    await session.flush()
    session.add_all(
        [
            JdRequirement(
                job_posting_id=posting.id,
                category="required",
                text="Python 개발 3년",
                display_order=1,
                tech_tags=["Python"],
            ),
            JdRequirement(
                job_posting_id=posting.id,
                category="preferred",
                text="협업 경험",
                display_order=2,
                tech_tags=["Python"],
            ),
        ]
    )
    candidates = []
    for index in range(count):
        repo = Repository(
            user_id=user.id,
            github_repo_id=index + 1,
            name=f"r{index}",
            full_name=f"me/r{index}",
            languages={"Python": 75, "Java": 25},
            head_sha="a" * 40,
        )
        session.add(repo)
        await session.flush()
        analysis = RepoAnalysis(
            repository_id=repo.id,
            analysis_level="l1",
            head_sha="a" * 40,
            prompt_version="v1",
            model="test",
            status="succeeded",
            tech_stack=["Python"],
        )
        session.add(analysis)
        await session.flush()
        candidate = AnalysisRepoCandidate(
            analysis_job_id=run.id,
            repository_id=repo.id,
            base_rank=index + 1,
            batch_no=index // 4 + 1,
            batch_rank=index % 4 + 1,
            filter_status="eligible",
            selection_reason="base_rank_top",
            ranking_signals={
                "portfolio_mentioned": index == 0,
                "rule_eligible": True,
                "analysis": {
                    "analysis_id": str(analysis.id),
                    "head_sha": analysis.head_sha,
                    "prompt_version": "v1",
                    "status": "succeeded",
                    "error_code": None,
                },
            },
        )
        session.add(candidate)
        candidates.append(candidate)
    await session.commit()
    return run, candidates


async def test_match_storage_global_limit_null_score_and_card_contract(
    db_session: AsyncSession,
) -> None:
    run, candidates = await seed_run(db_session)
    rows = await refresh_matches(db_session, run.id)
    await db_session.commit()
    assert [r.repository_id for r in rows if r.is_recommended] == [
        c.repository_id for c in candidates[:5]
    ]
    assert all(row.score is None for row in rows)
    assert all(len(row.matched_requirement_ids) == 1 for row in rows)
    assert rows[0].candidate_source == "both"
    cards = await get_repository_cards(db_session, run.id, batch_no=1)
    payload = cards[0].model_dump(mode="json")
    assert payload["matchScore"] is None
    assert payload["languages"] == [
        {"name": "Python", "ratio": 75.0},
        {"name": "Java", "ratio": 25.0},
    ]
    assert payload["recommended"] is True
    assert "selected" not in payload and "selectable" not in payload


async def test_out_of_order_pages_recompute_existing_run_order(db_session: AsyncSession) -> None:
    run, candidates = await seed_run(db_session)
    snapshots = [c.ranking_signals for c in candidates[:4]]
    for candidate in candidates[:4]:
        candidate.ranking_signals = {}
    await db_session.commit()
    rows = await refresh_matches(db_session, run.id)
    await db_session.commit()
    assert [r.repository_id for r in rows if r.is_recommended] == [
        c.repository_id for c in candidates[4:]
    ]
    with pytest.raises(AppError) as caught:
        await get_repository_cards(db_session, run.id, batch_no=1)
    assert caught.value.reason == Reason.NOT_READY
    for candidate, snapshot in zip(candidates[:4], snapshots, strict=True):
        candidate.ranking_signals = snapshot
    await db_session.commit()
    rows = await refresh_matches(db_session, run.id)
    await db_session.commit()
    assert [r.repository_id for r in rows if r.is_recommended] == [
        c.repository_id for c in candidates[:5]
    ]


async def test_failed_partial_and_unmatched_are_distinct(db_session: AsyncSession) -> None:
    run, candidates = await seed_run(db_session, 4)
    for candidate, status in zip(candidates[:2], ["failed", "partial"], strict=True):
        candidate.ranking_signals = {
            **candidate.ranking_signals,
            "analysis": {
                **candidate.ranking_signals["analysis"],
                "status": status,
                "error_code": "llm_failed",
            },
        }
    analysis_id = uuid.UUID(candidates[2].ranking_signals["analysis"]["analysis_id"])
    analysis = await db_session.get(RepoAnalysis, analysis_id)
    assert analysis is not None
    analysis.tech_stack = []
    await db_session.commit()
    rows = await refresh_matches(db_session, run.id)
    await db_session.commit()
    assert [r.is_recommended for r in rows] == [False, False, False, True]
    cards = await get_repository_cards(db_session, run.id)
    assert [c.status for c in cards] == ["failed", "partial", "succeeded", "succeeded"]
    assert all(c.match_score is None for c in cards)
    assert cards[0].recommend_reason is None and cards[2].error_code is None


async def test_concurrent_refresh_is_idempotent_and_cannot_exceed_five(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        run, _ = await seed_run(session, 12)

    async def refresh() -> None:
        async with session_factory() as session, session.begin():
            await refresh_matches(session, run.id)

    await asyncio.gather(refresh(), refresh())
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(RepoMatchScore).where(RepoMatchScore.analysis_job_id == run.id)
            )
        ).all()
        assert len(rows) == 12
        assert sum(row.is_recommended for row in rows) == 5


async def test_inaccessible_and_foreign_owner_never_recommended(db_session: AsyncSession) -> None:
    run, candidates = await seed_run(db_session, 3)
    first = await db_session.get(Repository, candidates[0].repository_id)
    second = await db_session.get(Repository, candidates[1].repository_id)
    assert first is not None and second is not None
    first.is_accessible = False
    other = User(name="other")
    db_session.add(other)
    await db_session.flush()
    second.user_id = other.id
    candidates[2].filter_status = "excluded"
    candidates[2].filter_reason = "inaccessible"
    await db_session.commit()
    rows = await refresh_matches(db_session, run.id)
    assert not any(r.is_recommended for r in rows)
    assert await get_repository_cards(db_session, run.id) == []


async def test_card_read_cannot_mix_candidates_with_newer_matches(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with session_factory() as session:
        run, _ = await seed_run(session, 1)
        await refresh_matches(session, run.id)
        await session.commit()
    candidates_read = asyncio.Event()
    release_read = asyncio.Event()
    writer_started = asyncio.Event()
    writer_locked = asyncio.Event()
    original = queries.bound_analyses

    async def pause_after_candidates(session, candidates):
        candidates_read.set()
        await release_read.wait()
        return await original(session, candidates)

    monkeypatch.setattr(queries, "bound_analyses", pause_after_candidates)

    async def read_cards():
        async with session_factory() as session, session.begin():
            return await get_repository_cards(session, run.id)

    async def invalidate():
        async with session_factory() as session, session.begin():
            writer_started.set()
            await session.scalar(
                select(AnalysisJob).where(AnalysisJob.id == run.id).with_for_update()
            )
            writer_locked.set()
            await session.execute(
                delete(RepoMatchScore).where(RepoMatchScore.analysis_job_id == run.id)
            )

    reader = asyncio.create_task(read_cards())
    await asyncio.wait_for(candidates_read.wait(), timeout=5)
    writer = asyncio.create_task(invalidate())
    await asyncio.wait_for(writer_started.wait(), timeout=5)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(writer_locked.wait(), timeout=0.2)
    finally:
        release_read.set()
        result = await asyncio.gather(reader, writer, return_exceptions=True)
    assert isinstance(result[0], list) and result[0][0].recommended
