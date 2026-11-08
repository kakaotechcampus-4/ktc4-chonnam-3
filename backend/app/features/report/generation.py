"""생성 요청의 영구 소유권·명시 재시도와 Redis 큐 전달을 연결한다."""

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from anyio import CancelScope
from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewReport, InterviewSession, ReportDisagreement
from app.db.models.report import ReportGenerationRequest
from app.features.interview.prepare_lease import JOB_TIMEOUT_SECONDS
from app.shared.enums import Reason

JOB_SECONDS = JOB_TIMEOUT_SECONDS
LOCK_SECONDS = 300
ACTIVE = ("queued", "running")
logger = get_logger(__name__)
_RESERVE = """
local old = redis.call('GET', KEYS[1])
if ARGV[3] == 'retry' then
  local failure = redis.call('GET', KEYS[2]) or ''
  if failure ~= ARGV[4] then return 0 end
  if old and old ~= ARGV[5] and old ~= '1' then return 0 end
elseif old then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
if ARGV[3] == 'retry' then redis.call('DEL', KEYS[2]) end
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
return 1
"""
_FAIL = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2])
return 1
"""
_ABORT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
if ARGV[2] ~= '' then redis.call('SET', KEYS[2], ARGV[2], 'NX') end
return 1
"""


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value or "")


async def _eval(redis: ArqRedis, script: str, count: int, *args: str) -> object:
    return await cast(Awaitable[object], redis.eval(script, count, *args))


async def _abort_queue(
    db: AsyncSession, redis: ArqRedis, interview_id: UUID, request_id: UUID, prior_failure: str
) -> None:
    await db.rollback()
    await db.get(InterviewSession, interview_id, with_for_update=True)
    row = await db.get(
        ReportGenerationRequest, request_id, with_for_update=True, populate_existing=True
    )
    if row is not None and row.status != "queued":
        # 응답이 사라져도 이미 worker가 수락했다면 그 실행권을 취소하지 않는다.
        return
    if row is not None:
        row.status, row.error_code = "enqueue_failed", "queue_unavailable"
        await db.commit()
    await _eval(
        redis,
        _ABORT,
        2,
        f"report:gen:{interview_id}",
        f"report:fail:{interview_id}",
        str(request_id),
        prior_failure,
    )


async def latest(
    db: AsyncSession, interview_id: UUID, *, active: bool = False
) -> ReportGenerationRequest | None:
    query = select(ReportGenerationRequest).where(
        ReportGenerationRequest.interview_session_id == interview_id
    )
    if active:
        query = query.where(ReportGenerationRequest.status.in_(ACTIVE))
    return cast(
        ReportGenerationRequest | None,
        await db.scalar(
            query.order_by(
                ReportGenerationRequest.created_at.desc(), ReportGenerationRequest.id.desc()
            )
            .limit(1)
            .with_for_update()
        ),
    )


async def locked_interview(
    db: AsyncSession, interview_id: UUID, user_id: UUID | None = None
) -> InterviewSession:
    query = select(InterviewSession).where(InterviewSession.id == interview_id)
    if user_id is not None:
        query = query.where(InterviewSession.user_id == user_id)
    interview = await db.scalar(query.with_for_update().execution_options(populate_existing=True))
    if interview is None:
        raise AppError(Reason.NOT_FOUND)
    if interview.status != "completed":
        raise AppError(Reason.REPORT_UNAVAILABLE)
    return interview


async def enqueue(
    db: AsyncSession,
    redis: ArqRedis,
    *,
    interview_id: UUID,
    user_id: UUID,
    mode: str = "initial",
    disagreement: ReportDisagreement | None = None,
    actor: str | None = None,
) -> ReportGenerationRequest | None:
    await locked_interview(db, interview_id, user_id)
    report = await db.scalar(
        select(InterviewReport)
        .where(InterviewReport.interview_session_id == interview_id)
        .with_for_update()
    )
    if mode != "reassessment" and report is not None:
        raise AppError(Reason.REPORT_UNAVAILABLE)
    active = await latest(db, interview_id, active=True)
    now = datetime.now(UTC)
    if active is not None:
        if active.expires_at > now:
            if active.mode != mode:
                raise AppError(Reason.REPORT_UNAVAILABLE)
            if mode == "reassessment" and (
                disagreement is None or active.disagreement_id != disagreement.id
            ):
                raise AppError(Reason.REPORT_UNAVAILABLE)
            return active
        active.status, active.error_code = "stale", "generation_expired"
        await db.flush()
        # 만료는 모델 실패와 마찬가지로 GET의 자동 재호출을 허용하지 않는다.
        if mode == "initial":
            await db.commit()
            raise AppError(Reason.REPORT_UNAVAILABLE)
    previous = await latest(db, interview_id)
    failure = _text(await redis.get(f"report:fail:{interview_id}"))
    failed = bool(
        await db.scalar(
            select(ReportGenerationRequest.id)
            .where(
                ReportGenerationRequest.interview_session_id == interview_id,
                (ReportGenerationRequest.status.in_(("failed", "stale")))
                | (
                    (ReportGenerationRequest.status == "enqueue_failed")
                    & (ReportGenerationRequest.mode != "initial")
                ),
            )
            .limit(1)
        )
    )
    if mode == "initial" and (failure or failed):
        raise AppError(Reason.REPORT_UNAVAILABLE)
    if mode == "retry" and not (failure or failed):
        raise AppError(Reason.REPORT_UNAVAILABLE)
    if mode == "reassessment" and (
        report is None
        or disagreement is None
        or disagreement.status != "approved"
        or disagreement.source_revision != report.current_revision
    ):
        raise AppError(Reason.REPORT_UNAVAILABLE)
    request = ReportGenerationRequest(
        id=uuid4(),
        interview_session_id=interview_id,
        mode=mode,
        status="queued",
        expected_revision=report.current_revision if report else 0,
        disagreement_id=disagreement.id if disagreement else None,
        requested_by=actor or str(user_id),
        expires_at=now + timedelta(seconds=JOB_SECONDS),
    )
    db.add(request)
    await db.flush()
    reservation_mode = "retry" if mode == "retry" or (mode == "reassessment" and failed) else mode
    request_id = request.id
    try:
        # 큐 응답을 잃어도 다음 요청이 영구 실행권을 확인할 수 있게 먼저 확정한다.
        await db.commit()
        acquired = await _eval(
            redis,
            _RESERVE,
            2,
            f"report:gen:{interview_id}",
            f"report:fail:{interview_id}",
            str(request_id),
            str(LOCK_SECONDS),
            reservation_mode,
            failure,
            str(previous.id) if previous else "",
        )
        if not acquired:
            with CancelScope(shield=True):
                await _abort_queue(db, redis, interview_id, request_id, "")
            if mode != "initial":
                raise AppError(Reason.REPORT_UNAVAILABLE)
            return None
        job = await redis.enqueue_job("report_generate", str(interview_id), str(request_id))
        if job is None:
            raise RuntimeError("Report job was not queued")
    except BaseException as error:
        with CancelScope(shield=True):
            try:
                await _abort_queue(
                    db,
                    redis,
                    interview_id,
                    request_id,
                    failure if reservation_mode == "retry" else "",
                )
            except Exception:
                logger.warning("report_queue_cleanup_failed", request_id=str(request_id))
        if isinstance(error, (AppError, asyncio.CancelledError)):
            raise
        raise AppError(Reason.INTERNAL_ERROR) from None
    return request


async def claim(
    sessions: async_sessionmaker[AsyncSession], interview_id: UUID, request_id: UUID | None
