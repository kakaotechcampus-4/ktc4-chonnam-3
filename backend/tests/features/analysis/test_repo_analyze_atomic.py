"""새 L1 참조와 모든 페이지의 추천이 함께 확정되거나 취소되는지 검증한다."""

import asyncio

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.posting import JobPosting
from app.features.analysis.cards import get_repository_cards
from app.features.analysis.pipeline.steps import repo_analyze
from app.shared.enums import Reason
from tests.features.analysis.test_repo_analyze import SETTINGS, _model_reply, _read, _seed
from tests.features.analysis.test_repo_analyze_stages import collect


async def seed_pages(sessions):
    run_id, repo_ids = await _seed(sessions, count=2)
    async with sessions.begin() as session:
        posting = JobPosting(
            normalized_url="https://www.wanted.co.kr/wd/1",
            raw_url="https://www.wanted.co.kr/wd/1",
            parse_status="succeeded",
            skill_tags=["Python"],
        )
        session.add(posting)
        await session.flush()
        await session.execute(
            update(AnalysisJob).where(AnalysisJob.id == run_id).values(job_posting_id=posting.id)
        )
        await session.execute(
            update(AnalysisRepoCandidate)
            .where(AnalysisRepoCandidate.repository_id == repo_ids[1])
            .values(batch_no=2, batch_rank=1)
        )
    return run_id, repo_ids


async def analyze(sessions, collected, repo_ids):
    def handler(request):
        assert request.url.host != "api.github.com"
        return _model_reply(repo_ids)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await repo_analyze.analyze_collected_batch(
            sessions,
            collected,
            settings=SETTINGS,
            http_client=http,
            refresh_recommendations=True,
        )


async def test_autoflush_disabled_keeps_completed_page_ready_after_next_page_commit(
    session_factory,
):
    sessions = async_sessionmaker(
        session_factory.kw["bind"], expire_on_commit=False, autoflush=False
    )
    run_id, repo_ids = await seed_pages(sessions)
    first = await collect(sessions, run_id)
    await analyze(sessions, first, repo_ids[:1])
    async with sessions.begin() as session:
        cards = await get_repository_cards(session, run_id)
        assert len(cards) == 1 and cards[0].recommended

    second = await collect(sessions, run_id, batch_no=2)
    # 아직 L1이 없는 다음 페이지의 수집만으로 기존 페이지를 무효화하지 않는다.
    async with sessions.begin() as session:
        assert (await get_repository_cards(session, run_id))[0].recommended
    await analyze(sessions, second, repo_ids[1:])

    async with sessions.begin() as session:
        first_cards = await get_repository_cards(session, run_id)
        second_cards = await get_repository_cards(session, run_id, batch_no=2)
        assert [card.id for card in first_cards + second_cards] == repo_ids
        assert all(card.recommended for card in first_cards + second_cards)
        assert all(card.match_score is None for card in first_cards + second_cards)
        assert len((await session.scalars(select(RepoMatchScore))).all()) == 2


async def test_recommendation_failure_rolls_back_new_analysis_but_keeps_completed_page(
    session_factory,
):
    sessions = async_sessionmaker(
        session_factory.kw["bind"], expire_on_commit=False, autoflush=False
    )
    run_id, repo_ids = await seed_pages(sessions)
    first = await collect(sessions, run_id)
    await analyze(sessions, first, repo_ids[:1])
    candidates, analyses, _ = await _read(sessions, run_id)
    original_snapshot = candidates[0].ranking_signals["analysis"]
    original_analysis_id = analyses[0].id
    second = await collect(sessions, run_id, batch_no=2)
    async with sessions.begin() as session:
        # 실제 추천 선행 조건을 깨서 snapshot 저장 이후의 실패를 유도한다.
        await session.execute(update(JobPosting).values(parse_status="failed"))

    with pytest.raises(AppError) as caught:
        await analyze(sessions, second, repo_ids[1:])
    assert caught.value.reason == Reason.NOT_READY
    candidates, analyses, repositories = await _read(sessions, run_id)
    assert [row.id for row in analyses] == [original_analysis_id]
    assert candidates[0].ranking_signals["analysis"] == original_snapshot
    assert "analysis" not in candidates[1].ranking_signals
    assert repositories[1].readme_text == "Python service README"
    async with sessions.begin() as session:
        cards = await get_repository_cards(session, run_id)
        assert len(cards) == 1 and cards[0].recommended
        matches = list((await session.scalars(select(RepoMatchScore))).all())
        assert len(matches) == 2
        assert next(row for row in matches if row.repository_id == repo_ids[0]).is_recommended


async def test_reader_never_observes_deleted_matches_while_next_page_is_committing(
    session_factory, monkeypatch
):
    run_id, repo_ids = await seed_pages(session_factory)
    first = await collect(session_factory, run_id)
    await analyze(session_factory, first, repo_ids[:1])
    second = await collect(session_factory, run_id, batch_no=2)
    snapshots_bound = asyncio.Event()
    allow_refresh = asyncio.Event()
    reader_started = asyncio.Event()
    original = repo_analyze.refresh_matches

    async def paused_refresh(session, target_run_id):
        snapshots_bound.set()
        await allow_refresh.wait()
        return await original(session, target_run_id)

    async def read_first_page():
        async with session_factory.begin() as session:
            reader_started.set()
            return await get_repository_cards(session, run_id)

    monkeypatch.setattr(repo_analyze, "refresh_matches", paused_refresh)
    writer = asyncio.create_task(analyze(session_factory, second, repo_ids[1:]))
    reader = None
    try:
        await asyncio.wait_for(snapshots_bound.wait(), timeout=5)
        reader = asyncio.create_task(read_first_page())
        await asyncio.wait_for(reader_started.wait(), timeout=5)
        # 삭제와 재계산 사이에는 run 잠금으로 대기하고 commit 뒤의 완성된 카드를 읽는다.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(reader), timeout=0.2)
    finally:
        allow_refresh.set()
        await asyncio.wait_for(writer, timeout=5)
        if reader is not None:
            cards = await asyncio.wait_for(reader, timeout=5)
    assert reader is not None and len(cards) == 1 and cards[0].recommended
