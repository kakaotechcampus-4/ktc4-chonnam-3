"""품질 지표 이벤트 기록 helper.

이벤트 기록 실패는 핵심 트랜잭션을 실패시키지 않는다 (task-17).
INSERT 는 SAVEPOINT 안에서 실행하므로 DB 오류가 나도 바깥 트랜잭션은 유지된다.
"""

import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.metric import EVENT_NAMES, Event

logger = get_logger(__name__)


async def record_event(
    db: AsyncSession,
    event_name: str,
    *,
    user_id: uuid.UUID | None = None,
    analysis_job_id: uuid.UUID | None = None,
    interview_session_id: uuid.UUID | None = None,
    repository_id: uuid.UUID | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    """이벤트 1건을 기록한다. DB 오류는 로그만 남기고 삼킨다.

    event_name 이 EVENT_NAMES 에 없으면 프로그래밍 오류이므로 ValueError 를 올린다.
    """
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unknown event_name: {event_name}")
    try:
        async with db.begin_nested():
            db.add(
                Event(
                    event_name=event_name,
                    user_id=user_id,
                    analysis_job_id=analysis_job_id,
                    interview_session_id=interview_session_id,
                    repository_id=repository_id,
                    payload=payload or {},
                )
            )
            await db.flush()
    except SQLAlchemyError:
        logger.warning("event_record_failed", event_name=event_name, exc_info=True)


async def commit_events(db: AsyncSession) -> None:
    """이벤트만 남은 트랜잭션을 commit 한다. commit 실패는 로그만 남기고 rollback 한다.

    record_event 의 SAVEPOINT 는 INSERT 오류만 막는다. 이벤트 전용 commit 이 실패해도
    이미 끝난 업무 결과의 응답을 막지 않도록, 업무 commit 뒤에만 호출한다.
    """
    try:
        await db.commit()
    except SQLAlchemyError:
        logger.warning("event_commit_failed", exc_info=True)
        await db.rollback()
