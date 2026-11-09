"""DB의 프로필 갱신 의도를 유한 횟수로 큐에 전달하고 실행권을 검증한다."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import and_, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.core.logging import get_logger
from app.db.models import InterviewReport, InterviewSession, ProfileRefreshRequest, User
from app.features.interview.prepare_lease import JOB_TIMEOUT_SECONDS, LEASE_SECONDS
from app.workers.profile_refresh_queue import enqueue_refresh

MAX_DISPATCH_ATTEMPTS = 5
MAX_PAGES = 10
PAGE_SIZE = 100
type Sessions = async_sessionmaker[AsyncSession]
logger = get_logger(__name__)


async def ensure_request(
    db: AsyncSession, *, user_id: UUID, report_id: UUID, report_revision: int
) -> UUID:
    source = await db.scalar(
        select(InterviewReport.id)
        .join(InterviewSession, InterviewSession.id == InterviewReport.interview_session_id)
        .where(
            InterviewReport.id == report_id,
            InterviewSession.user_id == user_id,
            InterviewReport.current_revision == report_revision,
        )
    )
    if source is None:
        raise ValueError("Profile refresh requires an owned published report revision")
    now = datetime.now(UTC)
    identity = await db.scalar(
        insert(ProfileRefreshRequest)
        .values(
            user_id=user_id,
            report_id=report_id,
            report_revision=report_revision,
            next_attempt_at=now,
            expires_at=now + timedelta(days=1),
        )
        .on_conflict_do_nothing(constraint="uq_profile_refresh_report_revision")
        .returning(ProfileRefreshRequest.id)
    )
    if identity is None:
        identity = await db.scalar(
            select(ProfileRefreshRequest.id).where(
                ProfileRefreshRequest.report_id == report_id,
                ProfileRefreshRequest.report_revision == report_revision,
            )
        )
    assert identity is not None
    return identity


def _due(now: datetime) -> ColumnElement[bool]:
    return or_(
        and_(
            ProfileRefreshRequest.status == "pending", ProfileRefreshRequest.next_attempt_at <= now
        ),
        and_(
            ProfileRefreshRequest.status.in_(("queued", "running")),
            ProfileRefreshRequest.lease_expires_at <= now,
        ),
    )


def _defer(row: ProfileRefreshRequest, now: datetime, error: str) -> None:
    row.status = (
        "failed"
        if row.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS or row.expires_at <= now
        else "pending"
    )
    row.last_error, row.owner_token, row.lease_expires_at = error, None, None
    row.next_attempt_at = now + timedelta(
        seconds=min(300, 5 * 2 ** max(0, row.dispatch_attempts - 1))
    )
    if error == "profile_refresh_busy":
        # busy도 전달 회차에 포함한다. 회차는 오래된 worker를 막는 fencing 값이므로 줄이지 않는다.
        # 정상 집계와 경합한 경우 다음 전달은 worker 전체 상한 뒤로 늦춘다(최대 5회·24시간 유지).
        row.next_attempt_at = now + timedelta(seconds=JOB_TIMEOUT_SECONDS)


def _terminal_metadata(row: ProfileRefreshRequest, now: datetime) -> dict[str, object] | None:
    if row.status != "failed":
        return None
    cause = (
        "expired"
        if row.expires_at <= now
        else "attempt_limit"
        if row.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS
        else "task_failed"
    )
    return {
        "request_id": str(row.id),
        "report_id": str(row.report_id),
        "report_revision": row.report_revision,
        "dispatch_attempts": row.dispatch_attempts,
        "terminal_cause": cause,
        "error_code": row.last_error,
    }


async def dispatch(
    sessions: Sessions, redis: ArqRedis, request_id: UUID, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    terminal = None
    async with sessions.begin() as db:
        row = await db.get(ProfileRefreshRequest, request_id, with_for_update=True)
        if row is None or row.status not in {"pending", "queued", "running"}:
            return False
        due = row.next_attempt_at if row.status == "pending" else row.lease_expires_at
        if due is None or due > now:
            return False
        active = await db.scalar(
            select(User.id).where(User.id == row.user_id, User.status == "active")
        )
        if (
            active is None
            or row.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS
            or row.expires_at <= now
        ):
            row.status, row.last_error = (
                "failed",
                "profile_refresh_delivery_exhausted" if active else "profile_user_inactive",
            )
            row.owner_token = None
            terminal = _terminal_metadata(row, now)
        else:
            row.status, row.owner_token = "queued", None
            row.dispatch_attempts += 1
            row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            row.next_attempt_at = row.lease_expires_at
            user_id, attempt = row.user_id, row.dispatch_attempts
    if terminal is not None:
        # 확정된 종료만 기록한다. 본문·예외 문자열·공급자 주소는 포함하지 않는다.
        logger.warning("profile_refresh_terminal", **terminal)
        return False
    try:
        # 전달 회차는 DB가 발급한다. 완료 결과가 남은 이전 job ID와 충돌하지 않는다.
        await enqueue_refresh(
            redis,
            str(user_id),
            event_id=f"{request_id}:{attempt}",
            request_id=str(request_id),
            delivery_no=attempt,
        )
        return True
    except Exception:
        async with sessions.begin() as db:
            row = await db.get(ProfileRefreshRequest, request_id, with_for_update=True)
            if row is not None and row.status == "queued" and row.dispatch_attempts == attempt:
                _defer(row, now, "queue_unavailable")
                terminal = _terminal_metadata(row, now)
        if terminal is not None:
            logger.warning("profile_refresh_terminal", **terminal)
        return False


async def claim(sessions: Sessions, request_id: UUID, user_id: UUID, attempt: int) -> UUID | None:
    if type(attempt) is not int:
        return None
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        row = await db.get(ProfileRefreshRequest, request_id, with_for_update=True)
        if (
            row is None
            or row.user_id != user_id
            or row.status != "queued"
            or row.dispatch_attempts != attempt
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
            or row.expires_at <= now
        ):
            return None
        active = await db.scalar(select(User.id).where(User.id == user_id, User.status == "active"))
        if active is None:
            # 큐에 들어간 뒤 철회된 사용자도 모델 실행 전에 영구 종료한다.
            row.status, row.last_error = "failed", "profile_user_inactive"
            row.owner_token, row.lease_expires_at = None, None
            return None
        token = uuid4()
        row.status, row.owner_token = "running", token
        # worker 전체 상한보다 긴 실행권으로 정상 처리 중인 job을 재전달하지 않는다.
        row.lease_expires_at = now + timedelta(seconds=JOB_TIMEOUT_SECONDS + 30)
        row.next_attempt_at = row.lease_expires_at
        return token


async def current(sessions: Sessions, request_id: UUID, token: UUID) -> bool:
    async with sessions() as db:
        return (
            await db.scalar(
                select(ProfileRefreshRequest.id).where(
                    ProfileRefreshRequest.id == request_id,
                    ProfileRefreshRequest.status == "running",
                    ProfileRefreshRequest.owner_token == token,
                    ProfileRefreshRequest.lease_expires_at > datetime.now(UTC),
                )
            )
            is not None
        )


async def finish(
    sessions: Sessions,
    request_id: UUID,
    token: UUID,
    *,
    success: bool,
    retry: bool = False,
    error: str | None = None,
) -> bool:
    async with sessions.begin() as db:
        row = await db.get(ProfileRefreshRequest, request_id, with_for_update=True)
        if (
            row is None
            or row.status != "running"
            or row.owner_token != token
            or row.lease_expires_at is None
            or row.lease_expires_at <= datetime.now(UTC)
        ):
            return False
        if retry:
            _defer(row, datetime.now(UTC), error or "profile_refresh_interrupted")
        else:
            row.status, row.last_error = ("succeeded", None) if success else ("failed", error)
            row.owner_token, row.lease_expires_at = None, None
        terminal = _terminal_metadata(row, datetime.now(UTC))
    if terminal is not None:
        logger.warning("profile_refresh_terminal", **terminal)
    return True


async def wake_user(sessions: Sessions, user_id: UUID) -> None:
    async with sessions.begin() as db:
        await db.execute(
            update(ProfileRefreshRequest)
            .where(
                ProfileRefreshRequest.user_id == user_id,
                ProfileRefreshRequest.status == "pending",
                ProfileRefreshRequest.last_error == "profile_refresh_busy",
            )
            .values(next_attempt_at=datetime.now(UTC))
        )


async def recover(
    sessions: Sessions,
    redis: ArqRedis,
    *,
    now: datetime | None = None,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
) -> int:
    if (
        type(page_size) is not int
        or not 1 <= page_size <= PAGE_SIZE
        or type(max_pages) is not int
        or not 1 <= max_pages <= MAX_PAGES
    ):
        raise ValueError("Profile recovery requires bounded pages")
    now = now or datetime.now(UTC)
    cursor = None
    dispatched = 0
    for _ in range(max_pages):
        query = select(ProfileRefreshRequest.id, ProfileRefreshRequest.next_attempt_at).where(
            _due(now)
        )
        if cursor is not None:
            query = query.where(
                tuple_(ProfileRefreshRequest.next_attempt_at, ProfileRefreshRequest.id) > cursor
            )
        async with sessions() as db:
            rows = (
                await db.execute(
                    query.order_by(
                        ProfileRefreshRequest.next_attempt_at, ProfileRefreshRequest.id
                    ).limit(page_size)
                )
            ).all()
        if not rows:
            break
        for identity, _ in rows:
            dispatched += await dispatch(sessions, redis, identity, now=now)
        cursor = (rows[-1][1], rows[-1][0])
        if len(rows) < page_size:
            break
    return dispatched
