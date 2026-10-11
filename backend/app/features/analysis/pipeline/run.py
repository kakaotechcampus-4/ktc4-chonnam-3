"""짧은 DB 트랜잭션 사이에서 분석 7단계를 실행한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidatePage
from app.db.models.document import UserDocument
from app.features.analysis.candidates import prepare_candidates
from app.features.analysis.matching import refresh_matches
from app.features.analysis.pipeline.run_completion import finish_page, finish_run
from app.features.analysis.pipeline.run_state import elapsed, step
from app.features.analysis.pipeline.run_support import (
    RunFailure,
    account_for_run,
    batch_outcome,
    collect,
    failure_code,
)
from app.features.analysis.pipeline.steps.repo_analyze import (
    analyze_collected_batch,
)
from app.features.analysis.posting_service import complete_posting, fetch_posting

logger = get_logger(__name__)


async def claim_run(ctx: dict[str, Any], run_id: UUID) -> AnalysisJob | None:
    db: AsyncSession
    async with ctx["session_factory"].begin() as db:
        run = await db.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.id == run_id,
                AnalysisJob.job_type == "analysis_run",
            )
            .with_for_update()
        )
        if run is None or run.status != "queued":
            return None
        syncing = await db.scalar(
            select(AnalysisJob.id).where(
                AnalysisJob.user_id == run.user_id,
                AnalysisJob.job_type == "initial_sync",
                AnalysisJob.status.in_(("queued", "running")),
            )
        )
        # 초기 목록 수집이 끝나기 전의 빈 DB를 no_public_repo로 오인하지 않는다.
        # 실행은 아직 시작하지 않았으므로 queued 상태를 reaper가 다시 등록한다.
        expired = run.created_at + timedelta(
            seconds=ctx["settings"].analysis_run_ttl_seconds
        ) <= datetime.now(UTC)
        if syncing is not None and not expired:
            return None
        now = datetime.now(UTC)
        run.status, run.started_at = "running", now
        run.queue_wait_ms = elapsed(run.queued_at, now)
        await db.flush()
        db.expunge(run)
        return run


async def run_analysis(ctx: dict[str, Any], run_id: UUID) -> None:
    run = await claim_run(ctx, run_id)
    if run is None:
        return
    try:
        if run.created_at + timedelta(
            seconds=ctx["settings"].analysis_run_ttl_seconds
        ) <= datetime.now(UTC):
            raise RunFailure("run_expired")
        await account_for_run(ctx, run.user_id)
        names: list[str] = []
        if run.document_id:
            async with step(ctx, run_id, "doc_extract"):
                async with ctx["session_factory"]() as db:
                    document = await db.scalar(
                        select(UserDocument).where(
                            UserDocument.id == run.document_id,
                            UserDocument.user_id == run.user_id,
                            UserDocument.doc_type == "portfolio",
                        )
                    )
                    if document is None or document.extract_status == "failed":
                        raise RunFailure("doc_extract_failed")
                    # preview에서 검증·저장한 URL을 사용한다. 원본 파일을 다시 추출하지 않는다.
                    names = [
                        urlsplit(url).path.strip("/") for url in document.extracted_github_urls
                    ]
        async with step(ctx, run_id, "repo_select"):
            empty_reason = "no_public_repo"
            async with ctx["session_factory"].begin() as db:
                candidates = await prepare_candidates(
                    db,
                    run_id,
                    portfolio_full_names=names,
                    min_size_kb=ctx["settings"].repo_min_size_kb,
                )
                eligible = any(
                    c.batch_no == 1 and c.filter_status == "eligible" for c in candidates
                )
                if not candidates:
                    latest_sync = await db.scalar(
                        select(AnalysisJob)
                        .where(
                            AnalysisJob.user_id == run.user_id,
                            AnalysisJob.job_type == "initial_sync",
                        )
                        .order_by(AnalysisJob.created_at.desc())
                        .limit(1)
                    )
                    # 수집 실패로 비어 있는 DB는 실제 공개 저장소가 없는 경우와 다르다.
                    if latest_sync is None or latest_sync.status != "succeeded":
                        empty_reason = (
                            latest_sync.error_code if latest_sync else None
                        ) or "internal_error"
                if eligible:
                    now = datetime.now(UTC)
                    db.add(
                        AnalysisRepoCandidatePage(
                            analysis_job_id=run_id,
                            page_no=1,
                            status="running",
                            requested_at=run.queued_at,
                            started_at=now,
                        )
                    )
            # 제외 원인을 commit한 다음 중단한다. 예외로 후보 기록까지 rollback하지 않는다.
            if not eligible:
                raise RunFailure(empty_reason)
        async with step(ctx, run_id, "repo_detail"):
            collected = await collect(ctx, run, 1)
        async with step(ctx, run_id, "jd_fetch"):
            if run.posting_url is None:
                raise RunFailure("jd_fetch_failed")
            prepared = await fetch_posting(
                ctx["session_factory"],
                run.posting_url,
                client=ctx["http_client"],
                reuse_ttl_days=ctx["settings"].jd_reuse_ttl_days,
            )
        async with step(ctx, run_id, "jd_extract"):
            posting = await complete_posting(ctx["session_factory"], prepared)
            async with ctx["session_factory"].begin() as db:
                saved = await db.get(AnalysisJob, run_id)
                assert saved is not None
                saved.job_posting_id = posting.id
        async with step(ctx, run_id, "repo_analyze"):
            snapshots = await analyze_collected_batch(
                ctx["session_factory"],
                collected,
                settings=ctx["settings"].require_llm(),
                http_client=ctx["http_client"],
                refresh_recommendations=True,
            )
            status, error = batch_outcome(snapshots)
            if status == "failed":
                raise RunFailure(error or "llm_failed")
        async with step(ctx, run_id, "match_score"):
            async with ctx["session_factory"].begin() as db:
                await refresh_matches(db, run_id)
        await finish_run(ctx, run_id, status, error)
    except asyncio.CancelledError:
        await finish_run(ctx, run_id, "failed", "internal_error")
        raise
    except Exception as error:
        code = failure_code(error)
        logger.warning("analysis_run_failed", run_id=str(run_id), error_code=code)
        await finish_run(ctx, run_id, "failed", code)


async def run_candidate_page(ctx: dict[str, Any], run_id: UUID, page: int) -> None:
    if page < 2:
        return
    async with ctx["session_factory"].begin() as db:
        run = await db.get(AnalysisJob, run_id)
        row = await db.scalar(
            select(AnalysisRepoCandidatePage)
            .where(
                AnalysisRepoCandidatePage.analysis_job_id == run_id,
                AnalysisRepoCandidatePage.page_no == page,
            )
            .with_for_update()
        )
        if (
            run is None
            or run.status not in {"succeeded", "partial"}
            or row is None
            or row.status != "pending"
        ):
            return
        row.status, row.started_at = "running", datetime.now(UTC)
        db.expunge(run)
    try:
        if run.created_at + timedelta(
            seconds=ctx["settings"].analysis_run_ttl_seconds
        ) <= datetime.now(UTC):
            raise RunFailure("run_expired")
        collected = await collect(ctx, run, page)
        snapshots = await analyze_collected_batch(
            ctx["session_factory"],
            collected,
            settings=ctx["settings"].require_llm(),
            http_client=ctx["http_client"],
            refresh_recommendations=True,
        )
        status, error = batch_outcome(snapshots)
        await finish_page(ctx, run_id, page, error if status == "failed" else None)
    except asyncio.CancelledError:
        await finish_page(ctx, run_id, page, "internal_error")
        raise
    except Exception as error:
        await finish_page(ctx, run_id, page, failure_code(error))
