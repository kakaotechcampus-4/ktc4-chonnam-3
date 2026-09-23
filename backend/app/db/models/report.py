"""interview_reports, report_scores, report_disagreements.

report_persona_feedbacks 는 만들지 않는다 — persona 별 피드백은
interview_reports.feedback_json 에 저장한다 (docs/db-schema.md 주요 결정).

docs/db-schema.md 리포트 절 / task-02
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, check_in
from app.db.models.interview import PERSONAS

# openapi ScoreKey 6종. totalScore 는 이 6개의 단순 평균이다 — 가중치를 쓰지 않는다.
SCORE_KEYS = (
    "project_understanding",
    "technical_reasoning",
    "problem_solving",
    "communication",
    "contribution_clarity",
    "company_job_fit",
)
# openapi ReasonType
DISAGREEMENT_REASON_TYPES = (
    "factual_error",
    "insufficient_basis",
    "overly_harsh",
    "unclear_intent",
    "other",
)


class InterviewReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """면접 1건당 리포트 1개. lazy generation 이라 면접 종료 직후에는 없다."""

    __tablename__ = "interview_reports"
    __table_args__ = (
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="interview_reports_total"),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # report_scores 6개의 단순 평균. 0~100.
    total_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    # persona 별 피드백 [{persona, tags, strengths, improvements}] — 별도 테이블을 두지 않는다.
    feedback_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    # {totalRequirements, coveredRequirements, uncoveredRequirements[]}
    coverage_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportScore(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """항목별 점수. label 은 score_criteria.label_ko 에서 온다."""

    __tablename__ = "report_scores"
    __table_args__ = (
        UniqueConstraint("report_id", "score_key", name="uq_report_scores_report_key"),
        CheckConstraint(check_in("score_key", SCORE_KEYS), name="report_scores_key"),
        CheckConstraint("score >= 0 AND score <= 100", name="report_scores_range"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_reports.id", ondelete="CASCADE"), nullable=False
    )
    score_key: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 이 점수의 근거가 된 턴. 채점 근거를 되짚을 수 있어야 한다.
    evidence_turn_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )


class ReportDisagreement(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """사용자 이의 제기. Sprint 1 은 테이블만 만들고 API·row 생성은 Sprint 2 다."""

    __tablename__ = "report_disagreements"
    __table_args__ = (
        # persona 당 1회. 재제출은 already_submitted 로 막는다.
        UniqueConstraint("report_id", "persona", name="uq_report_disagreements_report_persona"),
        CheckConstraint(check_in("persona", PERSONAS), name="report_disagreements_persona"),
        CheckConstraint(
            check_in("reason_type", DISAGREEMENT_REASON_TYPES),
            name="report_disagreements_reason_type",
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_reports.id", ondelete="CASCADE"), nullable=False
    )
    persona: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_type: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
