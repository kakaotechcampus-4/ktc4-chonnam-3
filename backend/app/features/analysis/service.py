"""run 생성 / 중복 방지 / 만료 판정 / 카드 변환. 트랜잭션과 commit 책임을 가진다.

중복 방지는 두 겹이다.
- DB 부분 유니크 `(user_id, job_type) WHERE status IN ('queued','running')`
- Redis 락 `run:lock:{userId}:analysis:{fingerprint}`
같은 fingerprint 면 기존 runId 를 재사용하고, 다른 fingerprint 면 409 run_in_progress 다.

status = queued / running / succeeded / partial / failed / canceled.
FE 는 partial 을 failed 로 보지만 result 조회는 계속 가능하다.

확정본 §3 analysis_jobs / task-11
"""

import hashlib
import uuid
from datetime import timedelta

import structlog
from arq.connections import ArqRedis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ErrorReason
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidatePage
from app.db.models.posting import JobPosting
from app.db.models.user import User
from app.features.analysis import queries
from app.features.analysis.progress import initial_steps
from app.features.analysis.schemas import (
    AnalysisRunResponse,
    AnalysisRunResultResponse,
    AnalyzingResponse,
    CandidatePageResponse,
    CreateAnalysisRunResponse,
    FailedRepository,
    JdRequirementItem,
    LanguageRatio,
    RepositoryCard,
    StepState,
)
from app.integrations.jd.base import JdUnsupportedSite
from app.integrations.jd.resolver import normalize_posting_url
from app.realtime.bus import (
    CANDIDATE_PAGE_LOCK_KEY,
    CANDIDATE_PAGE_LOCK_TTL_SECONDS,
    RUN_LOCK_KEY,
    RUN_LOCK_TTL_SECONDS,
    get_redis,
)
from app.shared.clock import now
from app.shared.enums import (
    JOB_STATUS_TO_RUN_STATUS,
    STEP_ORDER,
    CandidatePageStatus,
    CandidateSource,
    JobStatus,
    JobType,
    RepoStatus,
    RequirementType,
    RunStatus,
    StepStatus,
)

logger = structlog.get_logger(__name__)

ANALYSIS_RUN_TASK = "analysis_run"
CANDIDATE_PAGE_TASK = "candidate_page_analyze"


def build_fingerprint(
    user_id: uuid.UUID, normalized_url: str, document_id: uuid.UUID | None
) -> str:
    """user_id + normalized posting_url + documentId 로 run 재사용 키를 만든다."""
    raw = f"{user_id}|{normalized_url}|{document_id or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_run(
    db: AsyncSession,
    arq: ArqRedis,
    user: User,
    *,
    posting_url: str,
    document_id: uuid.UUID | None,
) -> CreateAnalysisRunResponse:
    """POST /analysis-runs. 공고 수집 실패는 여기서 판정하지 않는다(잡 생성 후 failureReason)."""
    settings = get_settings()
    url = posting_url.strip()
    if not url:
        raise AppError(ErrorReason.POSTING_URL_REQUIRED)
    try:
        normalized_url = normalize_posting_url(url)
    except JdUnsupportedSite as exc:
        raise AppError(ErrorReason.UNSUPPORTED_SITE) from exc

    if document_id is not None and await queries.get_document(db, document_id, user.id) is None:
        raise AppError(ErrorReason.DOCUMENT_NOT_FOUND)

    fingerprint = build_fingerprint(user.id, normalized_url, document_id)
    existing = await queries.find_active_run(db, user.id)
    if existing is not None:
        return _reuse_or_conflict(existing, fingerprint)

    await _acquire_run_lock(user.id, fingerprint)

    job = AnalysisJob(
        user_id=user.id,
        job_type=str(JobType.ANALYSIS_RUN),
        status=str(JobStatus.QUEUED),
        fingerprint=fingerprint,
        posting_url=url,
        normalized_posting_url=normalized_url,
        document_id=document_id,
        steps=initial_steps(),
        progress=0,
        expires_at=now() + timedelta(seconds=settings.analysis_run_ttl_seconds),
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        # 부분 유니크 충돌 = 그 사이에 다른 요청이 run 을 만들었다.
        await db.rollback()
        concurrent = await queries.find_active_run(db, user.id)
        if concurrent is None:  # pragma: no cover - 경합 직후 종료된 경우
            raise
        return _reuse_or_conflict(concurrent, fingerprint)

    await db.refresh(job)
    await arq.enqueue_job(ANALYSIS_RUN_TASK, str(job.id))
    logger.info("analysis_run_created", run_id=str(job.id), user_id=str(user.id))
    return CreateAnalysisRunResponse(run_id=job.id, status=RunStatus.RUNNING, reused=False)


def _reuse_or_conflict(existing: AnalysisJob, fingerprint: str) -> CreateAnalysisRunResponse:
    if existing.fingerprint == fingerprint:
        return CreateAnalysisRunResponse(run_id=existing.id, status=RunStatus.RUNNING, reused=True)
    raise AppError(ErrorReason.RUN_IN_PROGRESS, details={"runId": str(existing.id)})


async def _acquire_run_lock(user_id: uuid.UUID, fingerprint: str) -> None:
    """Redis 락은 보조 수단이다. Redis 가 없어도 DB 부분 유니크가 중복을 막는다."""
    try:
        await get_redis().set(
            RUN_LOCK_KEY.format(user_id=user_id, fingerprint=fingerprint),
            "1",
            nx=True,
            ex=RUN_LOCK_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("run_lock_unavailable", user_id=str(user_id), error=str(exc))


# ── 조회 ─────────────────────────────────────────────────────────────
async def get_run_status(db: AsyncSession, user: User, run_id: uuid.UUID) -> AnalysisRunResponse:
    """GET /analysis-runs/{runId}. 분석 실패도 200 + failureReason 이다."""
    job = await _require_run(db, user, run_id)
    steps = job.steps or {}
    return AnalysisRunResponse(
        run_id=job.id,
        status=_run_status(job),
        progress=job.progress,
        steps=[
            StepState(key=key, status=StepStatus(steps.get(str(key), str(StepStatus.PENDING))))
            for key in STEP_ORDER
        ],
        failure_reason=job.error_code,
        estimated_seconds=None,
    )


async def get_run_result(
    db: AsyncSession, user: User, run_id: uuid.UUID
) -> AnalysisRunResultResponse:
    """GET /analysis-runs/{runId}/result. partial 도 조회 가능하다."""
    job = await _require_run(db, user, run_id)
    _guard_expired(job)
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise AppError(ErrorReason.NOT_READY)

    rows = await queries.list_candidate_rows(db, job.id, batch_no=1)
    cards = [_to_card(row) for row in rows]
    failed = [
        FailedRepository(repository_id=card.repository_id, error_code=card.error_code or "unknown")
        for card in cards
        if card.status == RepoStatus.FAILED
    ]

    position: str | None = None
    company_name: str | None = None
    requirements: list[JdRequirementItem] = []
    if job.job_posting_id is not None:
        posting = await db.get(JobPosting, job.job_posting_id)
        if posting is not None:
            position = posting.position
            company_name = posting.company_name
            requirements = [
                JdRequirementItem(
                    id=item.id,
                    type=RequirementType(item.requirement_type),
                    text=item.requirement_text,
                )
                for item in await queries.list_requirements(db, posting.id)
            ]

    mentioned = await _mentioned_repo_count(db, job)
    matched = await queries.count_portfolio_mentioned(db, job.id)
    return AnalysisRunResultResponse(
        run_id=job.id,
        status=_run_status(job),
        analyzed_count=len(cards) - len(failed),
        failed_count=len(failed),
        failed_repositories=failed,
        repositories=cards,
        position=position,
        company_name=company_name,
        jd_requirements=requirements,
        mentioned_repo_count=mentioned,
        matched_repo_count=matched,
    )


async def get_candidate_page(
    db: AsyncSession, arq: ArqRedis, user: User, run_id: uuid.UUID, page: int
) -> CandidatePageResponse | AnalyzingResponse:
    """완료 page 는 200, 미분석 page 는 enqueue 후 202 analyzing."""
    settings = get_settings()
    job = await _require_run(db, user, run_id)
    _guard_expired(job)

    rows = await queries.list_candidate_rows(db, job.id, batch_no=page)
    page_row = await queries.get_candidate_page(db, job.id, page)

    if page_row is not None and page_row.status == CandidatePageStatus.FAILED:
        raise AppError(
            ErrorReason.CANDIDATE_PAGE_FAILED, details={"errorCode": page_row.error_code or ""}
        )
    page_done = page_row is not None and page_row.status == CandidatePageStatus.SUCCEEDED
    if rows and (page == 1 or page_done):
        return CandidatePageResponse(
            run_id=job.id, page=page, repositories=[_to_card(row) for row in rows]
        )
    if not rows and page > await queries.max_batch_no(db, job.id):
        # 남은 후보가 없는 page. 분석할 것이 없으므로 빈 목록을 그대로 준다.
        if await _no_more_candidates(db, job, page):
            return CandidatePageResponse(run_id=job.id, page=page, repositories=[])

    await _enqueue_candidate_page(db, arq, job, page)
    return AnalyzingResponse(retry_after=settings.candidate_page_retry_after_seconds)


async def _no_more_candidates(db: AsyncSession, job: AnalysisJob, page: int) -> bool:
    settings = get_settings()
    total = await queries.count_eligible_candidates(db, job.id)
    return (page - 1) * settings.repo_candidate_limit >= total


async def _enqueue_candidate_page(
    db: AsyncSession, arq: ArqRedis, job: AnalysisJob, page: int
) -> None:
    """page 행 upsert + 중복 enqueue 방지(cand:lock)."""
    page_row = await queries.get_candidate_page(db, job.id, page)
    if page_row is None:
        page_row = AnalysisRepoCandidatePage(
            analysis_job_id=job.id,
            page_no=page,
            status=str(CandidatePageStatus.PENDING),
            requested_at=now(),
        )
        db.add(page_row)
    elif page_row.status not in (CandidatePageStatus.PENDING, CandidatePageStatus.RUNNING):
        page_row.status = str(CandidatePageStatus.PENDING)
        page_row.requested_at = now()
        page_row.error_code = None
    await db.commit()

    acquired = True
    try:
        acquired = bool(
            await get_redis().set(
                CANDIDATE_PAGE_LOCK_KEY.format(run_id=job.id, page=page),
                "1",
                nx=True,
                ex=CANDIDATE_PAGE_LOCK_TTL_SECONDS,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("candidate_page_lock_unavailable", run_id=str(job.id), error=str(exc))
    if acquired:
        await arq.enqueue_job(CANDIDATE_PAGE_TASK, str(job.id), page)


# ── 공통 ─────────────────────────────────────────────────────────────
async def _require_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> AnalysisJob:
    job = await queries.get_run(db, run_id, user.id)
    if job is None:
        raise AppError(ErrorReason.NOT_FOUND)
    return job


def _guard_expired(job: AnalysisJob) -> None:
    if job.expires_at is not None and job.expires_at < now():
        raise AppError(ErrorReason.RUN_EXPIRED)


def _run_status(job: AnalysisJob) -> RunStatus:
    return JOB_STATUS_TO_RUN_STATUS[JobStatus(job.status)]


async def _mentioned_repo_count(db: AsyncSession, job: AnalysisJob) -> int:
    """포트폴리오에서 뽑은 GitHub URL 개수 (matched 와 다르면 FE 가 안내 문구를 띄운다)."""
    if job.document_id is None:
        return 0
    document = await queries.get_document(db, job.document_id, job.user_id)
    return len(document.extracted_github_urls) if document else 0


def _to_card(row: queries.CandidateRow) -> RepositoryCard:
    """후보 + repo + (있으면) AI 산출물 -> 카드.

    repo_analyses 행이 없으면 L0 수집 결과만으로 상태를 정한다. AI L1 이 붙으면
    repo_analyses.status/error_code 가 우선한다.
    """
    repo = row.repository
    if row.analysis is not None:
        status = RepoStatus(row.analysis.status)
        error_code = row.analysis.error_code
    elif repo.fetch_error_code:
        status = RepoStatus.FAILED
        error_code = repo.fetch_error_code
    elif repo.fetch_level == "detail":
        status = RepoStatus.SUCCEEDED
        error_code = None
    else:
        status = RepoStatus.PARTIAL
        error_code = None

    score = row.match_score
    return RepositoryCard(
        repository_id=repo.id,
        full_name=repo.full_name,
        name=repo.name,
        description=repo.description,
        languages=_language_ratios(repo.languages, repo.primary_language),
        topics=list(repo.topics or []),
        stars=repo.stars,
        forks=repo.forks,
        commit_count=repo.commit_count,
        user_commit_count=repo.user_commit_count,
        pushed_at=repo.repo_pushed_at,
        status=status,
        error_code=error_code,
        recommended=bool(score.is_ai_recommended) if score else False,
        candidate_source=_candidate_source(row),
        recommend_reason=score.recommend_reason if score else None,
        match_score=float(score.match_score) if score and score.match_score is not None else None,
        matched_requirement_ids=list(score.matched_requirement_ids) if score else [],
    )


def _language_ratios(
    languages: dict[str, int] | None, primary_language: str | None
) -> list[LanguageRatio]:
    """GitHub languages(byte) -> 백분율. 아직 L0-b 전이면 primary_language 만 100%."""
    if not languages:
        return [LanguageRatio(name=primary_language, ratio=100.0)] if primary_language else []
    total = sum(languages.values())
    if total <= 0:
        return []
    return [
        LanguageRatio(name=name, ratio=round(size * 100 / total, 1))
        for name, size in sorted(languages.items(), key=lambda item: item[1], reverse=True)
    ]


def _candidate_source(row: queries.CandidateRow) -> CandidateSource:
    signals = row.candidate.ranking_signals or {}
    portfolio = bool(signals.get("portfolio_mentioned"))
    rule_filter = bool(signals.get("rule_filter_passed"))
    if portfolio and rule_filter:
        return CandidateSource.BOTH
    if portfolio:
        return CandidateSource.PORTFOLIO
    return CandidateSource.RULE_FILTER
