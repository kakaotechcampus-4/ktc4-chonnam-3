"""analysis_jobs, analysis_repo_candidates, analysis_repo_candidate_pages, repo_match_scores.

docs/db-schema.md / task-02

repo_match_scores 는 AI 매칭 결과가 들어오는 자리다. 점수 산식은 PENDING(AI-L07) 이므로
BE 는 저장된 값을 카드로 옮기기만 한다.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AnalysisJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """분석 run 1건. steps/progress 가 진행률 폴링 API 의 원본이다.

    부분 유니크 `(user_id, job_type) WHERE status IN ('queued','running')` 으로
    사용자당 동시 실행을 1개로 막는다. 같은 fingerprint 면 기존 run 을 재사용한다.
    """

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('initial_sync','analysis_run','interview_prep','deep_analysis')",
            name="analysis_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','partial','failed','canceled')",
            name="analysis_jobs_status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="analysis_jobs_progress"),
        Index(
            "uq_analysis_jobs_active_per_type",
            "user_id",
            "job_type",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("ix_analysis_jobs_user_fingerprint", "user_id", "fingerprint"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    posting_url: Mapped[str | None] = mapped_column(String(1000))
    normalized_posting_url: Mapped[str | None] = mapped_column(String(1000))
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_documents.id", ondelete="SET NULL")
    )
    steps: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisRepoCandidate(Base, UUIDPrimaryKeyMixin):
    """run 종속 repo 후보 순위. 랭킹 원본은 Postgres 이며 Redis 를 원본으로 쓰지 않는다."""

    __tablename__ = "analysis_repo_candidates"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "repository_id", name="uq_candidates_job_repo"),
        UniqueConstraint("analysis_job_id", "base_rank", name="uq_candidates_job_base_rank"),
        CheckConstraint(
            "selection_reason IN "
            "('portfolio_mentioned','base_rank_top','jd_signal','high_contribution','other')",
            name="candidates_selection_reason",
        ),
        CheckConstraint(
            "filter_status IN ('eligible','excluded')", name="candidates_filter_status"
        ),
        CheckConstraint(
            "filter_reason IS NULL OR filter_reason IN "
            "('private','fork','archived','no_language','too_small','inaccessible')",
            name="candidates_filter_reason",
        ),
        Index("ix_candidates_job_batch", "analysis_job_id", "batch_no", "batch_rank"),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    base_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_no: Mapped[int | None] = mapped_column(SmallInteger)
    batch_rank: Mapped[int | None] = mapped_column(SmallInteger)
    selection_reason: Mapped[str | None] = mapped_column(String(30))
    ranking_score: Mapped[float | None] = mapped_column(Numeric(6, 3))
    ranking_signals: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    filter_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'eligible'")
    )
    filter_reason: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class AnalysisRepoCandidatePage(Base, UUIDPrimaryKeyMixin):
    """'더 보기' page 단위 분석 상태. page job 은 run status 를 되돌리지 않는다."""

    __tablename__ = "analysis_repo_candidate_pages"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "page_no", name="uq_candidate_pages_job_page"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed')",
            name="candidate_pages_status",
        ),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class RepoMatchScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """JD x repo 매칭 결과. AI 가 채우고 BE 는 카드로 옮긴다."""

    __tablename__ = "repo_match_scores"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "repository_id", name="uq_match_scores_job_repo"),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    match_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    matched_requirement_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    recommend_reason: Mapped[str | None] = mapped_column(Text)
    is_ai_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
