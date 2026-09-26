"""analysis_jobs, repo_match_scores (410/409 용 컬럼 2개 추가 - §1.3).

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
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, check_in

# report_generate / profile_summary 는 analysis_jobs 행을 쓰지 않는다 (docs/pipeline.md 1절).
JOB_TYPES = ("initial_sync", "analysis_run", "candidate_page_analyze", "interview_prep")
# FE RunStatus 3종과 다르다. partial/failed/canceled -> FE failed 로 매핑한다.
JOB_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "canceled")
ACTIVE_JOB_STATUSES = ("queued", "running")

CANDIDATE_FILTER_STATUSES = ("eligible", "excluded")
CANDIDATE_FILTER_REASONS = (
    "private",
    "fork",
    "archived",
    "no_language",
    "too_small",
    "inaccessible",
)
# jd_signal 은 첫 batch 에 쓰지 않는다. JD 확보 뒤 후속 ranking 신호로만 쓴다.
CANDIDATE_SELECTION_REASONS = ("portfolio_mentioned", "base_rank_top", "high_contribution", "other")
CANDIDATE_PAGE_STATUSES = ("pending", "running", "succeeded", "failed")
# openapi CandidateSource
CANDIDATE_SOURCES = ("rule_filter", "portfolio", "both")


class AnalysisJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ARQ job 1건의 원본 상태. FE 의 runId 가 이 행의 id 다."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(check_in("job_type", JOB_TYPES), name="job_type"),
        CheckConstraint(check_in("status", JOB_STATUSES), name="status"),
        # 사용자·job_type 당 살아 있는 job 1개. 락 키에 job_type 이 들어가는 이유와 같다 —
        # M1 initial_sync 와 M2 analysis_run 이 겹쳐도 정상 흐름을 막지 않는다.
        Index(
            "uq_analysis_jobs_active_user_job_type",
            "user_id",
            "job_type",
            unique=True,
            postgresql_where=text(check_in("status", ACTIVE_JOB_STATUSES)),
        ),
        Index("ix_analysis_jobs_user_id_created_at", "user_id", "created_at"),
        Index("ix_analysis_jobs_fingerprint", "fingerprint"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    # initial_sync 에는 공고가 없다.
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True
    )
    posting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_documents.id", ondelete="SET NULL"), nullable=True
    )
    # user_id + normalized posting_url + document 해시. 중복 요청 재사용 판정에 쓴다.
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 7개 StepKey 전부를 담는다. 실행되지 않은 step 도 skipped 로 남긴다.
    steps: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    estimated_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ARQ 재시도나 reaper 재등록이 아니라 사용자가 누른 재시도 횟수다. 섞지 않는다.
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_wait_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AnalysisRepoCandidate(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """run 종속 repo 후보 순위. Redis 를 원본으로 쓰지 않는다."""

    __tablename__ = "analysis_repo_candidates"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "repository_id", name="uq_candidates_job_repo"),
        UniqueConstraint("analysis_job_id", "base_rank", name="uq_candidates_job_base_rank"),
        Index("ix_candidates_job_batch", "analysis_job_id", "batch_no", "batch_rank"),
        CheckConstraint(check_in("filter_status", CANDIDATE_FILTER_STATUSES), name="filter_status"),
        CheckConstraint(
            check_in("filter_reason", CANDIDATE_FILTER_REASONS) + " OR filter_reason IS NULL",
            name="filter_reason",
        ),
        CheckConstraint(
            check_in("selection_reason", CANDIDATE_SELECTION_REASONS)
            + " OR selection_reason IS NULL",
            name="selection_reason",
        ),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    # 전체 public repo 대상 L0-a lightweight ranking 순위
    base_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ranking_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    ranking_signals: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # 제외 repo 도 사유와 함께 남긴다. 기본 응답에는 eligible 만 노출한다.
    filter_status: Mapped[str] = mapped_column(String(20), nullable=False)
    filter_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)


class AnalysisRepoCandidatePage(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """더 보기 page 의 분석 상태. page job 은 run 전체 status 를 바꾸지 않는다."""

    __tablename__ = "analysis_repo_candidate_pages"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "page_no", name="uq_candidate_pages_job_page"),
        CheckConstraint(check_in("status", CANDIDATE_PAGE_STATUSES), name="status"),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class RepoMatchScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """match_score 단계 산출물. 추천 카드의 점수·이유·매칭 요구사항."""

    __tablename__ = "repo_match_scores"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "repository_id", name="uq_match_scores_job_repo"),
        CheckConstraint(check_in("candidate_source", CANDIDATE_SOURCES), name="candidate_source"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    matched_requirement_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    recommend_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    candidate_source: Mapped[str] = mapped_column(String(20), nullable=False)
