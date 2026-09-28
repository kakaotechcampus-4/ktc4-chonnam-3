"""인증된 분석 생성·조회·후보 페이지와 짧은 DB 트랜잭션 경계."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, AnalysisRepoCandidatePage
from app.db.models.document import UserDocument
from app.db.models.posting import JdRequirement, JobPosting
from app.db.models.user import GithubAccount
from app.features.analysis.cards import get_repository_cards
from app.features.analysis.posting_service import normalize_posting_url
from app.features.analysis.queue import enqueue_analysis
from app.features.analysis.run_queries import (
    allocate_page,
    assigned_candidates,
    candidate_page,
    owned_run,
)
from app.features.analysis.run_schemas import (
    AnalysisRunResponse,
    AnalysisRunResultResponse,
    AnalysisStep,
    AnalyzingResponse,
    CandidatesResponse,
    CreateAnalysisRunRequest,
    FailedRepository,
    JdRequirementResponse,
)
from app.integrations.jd.base import UnsupportedSiteError
from app.shared.enums import Reason, StepKey, StepStatus, to_run_status


def initial_steps(has_document: bool) -> list[dict[str, object]]:
    return [
        {
            "key": key.value,
            "status": "skipped" if key == StepKey.DOC_EXTRACT and not has_document else "pending",
        }
        for key in StepKey
    ]


def status_response(run: AnalysisJob) -> AnalysisRunResponse:
    saved = {item.get("key"): item.get("status") for item in run.steps}
    steps = [
        AnalysisStep(key=key, status=StepStatus(str(saved.get(key.value, "skipped"))))
        for key in StepKey
    ]
    counted = [step for step in steps if step.status != StepStatus.SKIPPED]
    progress = (
        round(100 * sum(s.status == StepStatus.COMPLETED for s in counted) / len(counted))
        if counted
        else 0
    )
    return AnalysisRunResponse(
        run_id=run.id,
        status=to_run_status(run.status),
        steps=steps,
        progress=progress,
        failure_reason=run.error_code,
        estimated_seconds=run.estimated_seconds,
    )


async def create_run(
    db: AsyncSession, user_id: UUID, request: CreateAnalysisRunRequest, redis: ArqRedis
) -> UUID:
    if request.posting_url is None or not request.posting_url.strip():
        raise AppError(Reason.POSTING_URL_REQUIRED)
    try:
        url = normalize_posting_url(request.posting_url.strip())
    except UnsupportedSiteError:
        raise AppError(Reason.UNSUPPORTED_SITE) from None
    account = await db.scalar(select(GithubAccount).where(GithubAccount.user_id == user_id))
    if account is None or account.token_status != "valid":
        raise AppError(Reason.GITHUB_TOKEN_INVALID)
    if request.document_id is not None:
        document = await db.scalar(
            select(UserDocument).where(
                UserDocument.id == request.document_id,
                UserDocument.user_id == user_id,
                UserDocument.doc_type == "portfolio",
            )
        )
        if document is None:
            raise AppError(Reason.INVALID_REQUEST)
        if document.extract_status == "failed":
            raise AppError(Reason.DOCUMENT_EXTRACT_FAILED)
    fingerprint = hashlib.sha256(
        json.dumps(
            [str(user_id), url, str(request.document_id) if request.document_id else None],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    while True:
        identity = await db.scalar(
            insert(AnalysisJob)
            .values(
                id=uuid4(),
                user_id=user_id,
                job_type="analysis_run",
                status="queued",
                posting_url=url,
                document_id=request.document_id,
                fingerprint=fingerprint,
                queued_at=datetime.now(UTC),
                steps=initial_steps(request.document_id is not None),
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "fingerprint"],
                index_where=text("status IN ('queued', 'running') AND job_type = 'analysis_run'"),
            )
            .returning(AnalysisJob.id)
        )
        if identity is not None:
            await db.commit()
            await enqueue_analysis(redis, identity)
            return identity
        existing = await db.scalar(
            select(AnalysisJob.id).where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.fingerprint == fingerprint,
                AnalysisJob.job_type == "analysis_run",
                AnalysisJob.status.in_(("queued", "running")),
            )
        )
        await db.commit()
        if existing is not None:
            raise AppError(Reason.RUN_IN_PROGRESS, details={"runId": str(existing)})
        # 충돌한 작업이 SELECT 전에 종료된 경우에만 새 INSERT를 시도한다.


async def get_status(
    db: AsyncSession, user_id: UUID, run_id: UUID, settings: Settings
) -> AnalysisRunResponse:
    result = status_response(
        await owned_run(db, run_id, user_id, settings.analysis_run_ttl_seconds)
    )
    await db.commit()
    return result


async def get_result(
    db: AsyncSession, user_id: UUID, run_id: UUID, settings: Settings
) -> AnalysisRunResultResponse:
    run = await owned_run(db, run_id, user_id, settings.analysis_run_ttl_seconds, lock=True)
    if run.status not in {"succeeded", "partial"} or run.job_posting_id is None:
        raise AppError(Reason.NOT_READY)
    posting = await db.get(JobPosting, run.job_posting_id)
    if posting is None:
        raise AppError(Reason.NOT_READY)
    cards = await get_repository_cards(db, run_id)
    requirements = list(
        await db.scalars(
            select(JdRequirement)
            .where(JdRequirement.job_posting_id == posting.id)
            .order_by(JdRequirement.display_order)
        )
    )
    candidates = await assigned_candidates(db, run_id)
    failed: list[FailedRepository] = []
    analyzed = 0
    all_candidates = await db.scalars(
        select(AnalysisRepoCandidate).where(AnalysisRepoCandidate.analysis_job_id == run_id)
    )
    # 포트폴리오에서 계정 저장소와 연결된 수는 페이지 조회 여부와 무관하다.
    matched = sum(
        bool((candidate.ranking_signals or {}).get("portfolio_mentioned"))
        for candidate in all_candidates
    )
    for candidate in candidates:
        signals = candidate.ranking_signals or {}
        snapshot = signals.get("analysis")
        if not isinstance(snapshot, dict):
            continue
        if snapshot.get("status") in {"succeeded", "partial"}:
            analyzed += 1
        elif snapshot.get("status") == "failed":
            failed.append(
                FailedRepository(
                    repository_id=candidate.repository_id,
                    error_code=str(snapshot.get("error_code") or "internal_error"),
                )
            )
    document = await db.get(UserDocument, run.document_id) if run.document_id else None
    mentioned = (
        len(set(url.casefold().rstrip("/") for url in document.extracted_github_urls))
        if document
        else 0
    )
    response = AnalysisRunResultResponse(
        run_id=run.id,
        position=posting.position or "",
        company_name=posting.company_name,
        jd_requirements=[JdRequirementResponse.model_validate(row) for row in requirements],
        mentioned_repo_count=mentioned,
        matched_repo_count=matched,
        repositories=cards,
        analyzed_count=analyzed,
        failed_count=len(failed),
        failed_repositories=failed,
    )
    await db.commit()
    return response


async def get_candidates(
    db: AsyncSession, user_id: UUID, run_id: UUID, page: int, settings: Settings, redis: ArqRedis
) -> CandidatesResponse | AnalyzingResponse:
    run = await owned_run(db, run_id, user_id, settings.analysis_run_ttl_seconds, lock=True)
    if run.status in {"queued", "running"}:
        await db.commit()
        return AnalyzingResponse()
    if run.status not in {"succeeded", "partial"}:
        raise AppError(Reason.NOT_READY)
    # page_no는 PostgreSQL INTEGER다. 표현할 수 없는 양수도 범위 밖 빈 페이지다.
    if page > 2**31 - 1:
        await db.commit()
        return CandidatesResponse(repositories=[])
    row = await candidate_page(db, run_id, page)
    if row is not None and row.status == "failed":
        raise AppError(Reason.CANDIDATE_PAGE_FAILED)
    if row is not None and row.status == "succeeded":
        cards = await get_repository_cards(db, run_id, batch_no=page)
        await db.commit()
        return CandidatesResponse(repositories=cards)
    if row is None:
        if not await allocate_page(db, run_id, page, settings.repo_candidate_limit):
            await db.commit()
            return CandidatesResponse(repositories=[])
        row = AnalysisRepoCandidatePage(
            analysis_job_id=run_id, page_no=page, status="pending", requested_at=datetime.now(UTC)
        )
        db.add(row)
    enqueue = row.status == "pending"
    await db.commit()
    if enqueue:
        await enqueue_analysis(redis, run_id, page)
    return AnalyzingResponse()
