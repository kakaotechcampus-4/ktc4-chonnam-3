"""events, feedback_signals, eval_cases, eval_runs.

Sprint 1 에 만드는 것은 events 뿐이다. feedback_signals / eval_cases / eval_runs 는
Sprint 2 로 미룬다 (docs/db-schema.md).

docs/layer-rules.md 1절 / task-02
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, check_in

# task-17 이 고정한 10종. 이 목록 밖의 event_name 은 INSERT 가 거부된다.
#
# ⚠ docs/pipeline.md 4.2 절은 session_started / session_completed / session_abandoned 로
#   적혀 있어 이름이 다르다. task-17 이 "Sprint 1 이벤트 목록은 위 10개로 고정한다" 고
#   명시했으므로 task-17 을 따른다. 명시적 abandoned 가 발생해도 별도 이벤트를 두지 않는다.
EVENT_NAMES = (
    "analysis_run_started",
    "analysis_run_completed",
    "analysis_run_failed",
    "repo_recommended",
    "repo_selected",
    "interview_started",
    "turn_asked",
    "turn_answered",
    "interview_completed",
    "report_viewed",
)


class Event(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """품질 지표용 append-only 이벤트.

    이벤트 기록 실패가 핵심 트랜잭션을 실패시키지 않아야 하므로 FK 는 전부 nullable 이고
    삭제 시 SET NULL 이다.
    """

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(check_in("event_name", EVENT_NAMES), name="events_event_name"),
        Index("ix_events_event_name_created_at", "event_name", "created_at"),
        Index("ix_events_user_id_created_at", "user_id", "created_at"),
    )

    event_name: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    analysis_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True
    )
    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    # 이벤트별 부가 정보. 지표 쿼리가 읽는다 (평균 depth, evidence tool 사용 비율 등).
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default="{}")
