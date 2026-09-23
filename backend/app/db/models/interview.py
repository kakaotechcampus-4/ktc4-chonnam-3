"""interview_sessions, session_repositories, interview_turns.

★ interview_turns.topic_code 는 1차에 FK 를 걸지 않는다 (topic_taxonomy 확정 후 2차).
★ persona CHECK = tech_lead / hr_manager / domain_lead.
★ turn_evidences PK = (turn_id, evidence_id, usage) — 같은 evidence 가 질문 근거이면서
  채점 근거일 수 있다. (turn_evidences 는 models/evidence.py 에 있다)

docs/db-schema.md / task-02
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, check_in

# DB 5종. FE InterviewStatus 와 값이 같다 (docs/pipeline.md 4.5).
INTERVIEW_STATUSES = ("preparing", "preparing_failed", "in_progress", "completed", "abandoned")
# 준비 중이거나 진행 중인 면접. run 당 1개만 허용한다.
ACTIVE_INTERVIEW_STATUSES = ("preparing", "in_progress")
# Sprint 1 은 양방향 텍스트 고정. 음성은 Sprint 2.
ANSWER_MODES = ("text",)
PERSONAS = ("tech_lead", "hr_manager", "domain_lead")
TURN_STATUSES = ("asked", "answered")


class InterviewSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """면접 1건. 이 행의 id 가 영구 식별자인 interviewId 다.

    실시간 sessionId 는 Redis rt:{sessionId} 에만 있고 DB 에 두지 않는다
    (docs/pipeline.md 4.4).
    """

    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(check_in("status", INTERVIEW_STATUSES), name="interview_sessions_status"),
        CheckConstraint(
            check_in("answer_mode", ANSWER_MODES), name="interview_sessions_answer_mode"
        ),
        # 같은 run 에 활성 면접 1개만 (session_limit_exceeded).
        Index(
            "uq_interview_sessions_active_per_run",
            "analysis_job_id",
            unique=True,
            postgresql_where=text(check_in("status", ACTIVE_INTERVIEW_STATUSES)),
        ),
        Index("ix_interview_sessions_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # FE 의 runId. 새로고침 후 레포 선택 화면으로 돌아가는 경로가 된다.
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True
    )
    # retry 로 만든 세션이면 원본을 가리킨다. 원본의 run·공고·repo 조합을 복사한다.
    retry_of_interview_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="preparing")
    answer_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="text")
    total_turns: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="9")
    current_turn: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    # Director 작업 기억의 원본. Redis snapshot 이 날아가면 여기서 재구성한다.
    context_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # PrepareStepKey 4종의 진행 상태. preparing_failed 화면 복구에 쓴다.
    prepare_steps: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    # {reason, code, step, recoverable, occurredAt} — WS error 이벤트와 같은 모양.
    last_error: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at_turn: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class SessionRepository(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """면접에 선택된 repo. 1개 이상 5개 이하."""

    __tablename__ = "session_repositories"
    __table_args__ = (
        UniqueConstraint(
            "interview_session_id", "repository_id", name="uq_session_repositories_session_repo"
        ),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    # L2 deep analysis 대상 1~2개. 기술 질문은 이 repo 중심으로 만든다.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # AI 추천 채택률 지표의 원천 (task-17 의 selection_source=ai_removed 집계).
    # 값 집합은 task-17 에서 확정하므로 아직 CHECK 를 걸지 않는다.
    selection_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InterviewTurn(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """질문/답변 1턴. 질문 INSERT 와 turn_evidences INSERT 는 같은 트랜잭션으로 묶는다."""

    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("interview_session_id", "turn_no", name="uq_interview_turns_session_turn"),
        CheckConstraint(check_in("persona", PERSONAS), name="interview_turns_persona"),
        CheckConstraint(check_in("status", TURN_STATUSES), name="interview_turns_status"),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    persona: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="asked")

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 꼬리질문 깊이. parent_turn_no 는 어느 턴을 파고든 질문인지.
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    parent_turn_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Sprint 1 은 FK 를 걸지 않는다 (topic_taxonomy 확정 후 Sprint 2).
    topic_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # domain_lead 는 jd_requirement_ids, hr_manager 는 claim_ids 가 근거가 될 수 있다.
    jd_requirement_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    claim_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )

    # AnswerAnalysis / DirectorDecision 원문. 별도 테이블은 Sprint 2.
    analysis: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    decision: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
