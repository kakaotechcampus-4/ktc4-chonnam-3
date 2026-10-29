"""준비 작업의 소유권·갱신·만료 경계를 DB 원본에서 관리한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.db.models import InterviewSession

STEPS = ("analyze_repo", "build_persona", "set_criteria", "compose_question")
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20
JOB_TIMEOUT_SECONDS = 600
CLAIM_KEYS = {"prepare_job_id", "prepare_lease_expires_at", "prepare_director_call_id"}
logger = get_logger(__name__)


class PreparationTimeoutError(ValueError):
    """유효한 호출 설정이어도 worker의 준비 시간 안에 끝낼 수 없는 조합이다."""


def expires(row: InterviewSession) -> datetime:
    value = (row.context_state or {}).get("prepare_lease_expires_at")
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    # 이전 작성본의 claim도 영구 고착시키지 않으며 마지막 DB 수정 이후로 제한한다.
    return (
        parsed
        if parsed is not None and parsed.tzinfo
        else row.updated_at + timedelta(seconds=LEASE_SECONDS)
    )


def owns_preparation(row: InterviewSession, *, job_id: UUID, now: datetime | None = None) -> bool:
    return (
        row.status == "preparing"
        and (row.context_state or {}).get("prepare_job_id") == str(job_id)
        and expires(row) > (now or datetime.now(UTC))
    )


def claim(row: InterviewSession, job_id: UUID) -> None:
    row.context_state = {
        **(row.context_state or {}),
        "prepare_job_id": str(job_id),
        "prepare_lease_expires_at": (
            datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        ).isoformat(),
    }


def clear(row: InterviewSession) -> None:
    row.context_state = {
        key: value for key, value in (row.context_state or {}).items() if key not in CLAIM_KEYS
    }


def completed(row: InterviewSession) -> int:
    checkpoint = (row.context_state or {}).get("preparation_checkpoint")
    value = checkpoint.get("completed") if isinstance(checkpoint, dict) else 0
    return value if type(value) is int and 0 <= value <= 3 else 0


def steps(row: InterviewSession, *, failed: str | None = None) -> list[dict[str, object]]:
    count = completed(row)
    return [
        {
            "step": step,
            "status": "failed"
            if step == failed
            else ("completed" if index < count else "running" if index == count else "pending"),
        }
        for index, step in enumerate(STEPS)
    ]


def failed(row: InterviewSession, code: str, step: str, *, recoverable: bool = True) -> None:
    row.status, row.prepare_steps = "preparing_failed", steps(row, failed=step)
    row.last_error = dict(
        reason="prep_failed",
        code=code,
        step=step,
        recoverable=recoverable,
        occurredAt=datetime.now(UTC).isoformat(),
    )
    clear(row)


async def refresh(
    sessions: async_sessionmaker[AsyncSession], interview_id: UUID, job_id: UUID
) -> bool:
    async with sessions.begin() as db:
        row = await db.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == interview_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or not owns_preparation(row, job_id=job_id):
            return False
        claim(row, job_id)
        return True


def heartbeat(
    sessions: async_sessionmaker[AsyncSession], interview_id: UUID, job_id: UUID
) -> asyncio.Task[None]:
    owner = asyncio.current_task()
    assert owner is not None

    async def renew() -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                if not await refresh(sessions, interview_id, job_id):
                    owner.cancel()
                    return
        except SQLAlchemyError:
            # DB 소유권을 확인하지 못하면 결과를 계속 발행하지 않는다.
            logger.warning(
                "interview_prepare_heartbeat_unavailable", interview_id=str(interview_id)
            )
            owner.cancel()

    return asyncio.create_task(renew())


def validate_timeout(source_seconds: float, llm_seconds: float) -> None:
    # primary 두 개의 수집과 L2, 생성·검토에 여유 30초를 남긴다.
    if 2 * source_seconds + 4 * llm_seconds + 30 > JOB_TIMEOUT_SECONDS:
        raise PreparationTimeoutError("Preparation timeouts exceed the worker time budget")
