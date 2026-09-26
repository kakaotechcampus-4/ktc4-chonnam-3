"""Sprint 1 초기 스키마.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-21

수동 작성이다 (task-02). autogenerate 는 참고용으로만 썼다.

downgrade 가능 범위: 이 migration 이 만든 테이블을 전부 되돌린다.
pgcrypto extension 은 다른 스키마가 쓸 수 있어 되돌리지 않는다.
데이터는 복구하지 않는다 — 운영 DB 에서는 쓰지 않는다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블 생성 역순으로 지운다 (FK 의존).
_TABLES_IN_CREATE_ORDER = (
    "users",
    "github_accounts",
    "repositories",
    "repo_analyses",
    "user_profile_summaries",
    "job_postings",
    "jd_requirements",
    "user_documents",
    "document_claims",
    "analysis_jobs",
    "analysis_repo_candidates",
    "analysis_repo_candidate_pages",
    "repo_match_scores",
    "interview_sessions",
    "session_repositories",
    "interview_turns",
    "evidences",
    "turn_evidences",
    "evidence_conflicts",
    "interview_reports",
    "report_scores",
    "report_disagreements",
    "score_criteria",
    "prompt_versions",
    "domain_question_frames",
    "events",
)


def _uuid_pk() -> sa.Column[postgresql.UUID]:
    """UUID PK 컬럼. 기본값은 pgcrypto 의 gen_random_uuid()."""
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _create_account_tables() -> None:
    """users, github_accounts."""
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'withdrawn')",
            name="ck_users_status",
        ),
    )

    op.create_table(
        "github_accounts",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("public_repo_count", sa.Integer(), nullable=True),
        # 평문 저장 금지 — core/crypto.py 로 AES-GCM 암호화한 값만 들어간다.
        sa.Column("access_token_encrypted", postgresql.BYTEA(), nullable=False),
        sa.Column("token_status", sa.String(length=20), server_default="valid", nullable=False),
        sa.Column("token_scope", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_github_accounts"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_github_accounts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_github_accounts_user_id"),
        sa.UniqueConstraint("github_user_id", name="uq_github_accounts_github_user_id"),
        sa.CheckConstraint(
            "token_status IN ('valid', 'revoked', 'invalid')",
            name="ck_github_accounts_token_status",
        ),
    )


def _create_github_tables() -> None:
    """repositories, repo_analyses, user_profile_summaries."""
    op.create_table(
        "repositories",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_language", sa.Text(), nullable=True),
        sa.Column("languages", postgresql.JSONB(), nullable=True),
        sa.Column("topics", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=True),
        sa.Column("commit_count", sa.Integer(), nullable=True),
        sa.Column("user_commit_count", sa.Integer(), nullable=True),
        sa.Column("readme_text", sa.Text(), nullable=True),
        sa.Column("readme_truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("stars", sa.Integer(), server_default="0", nullable=False),
        sa.Column("forks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("size_kb", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_branch", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_fork", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_accessible", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_repositories"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_repositories_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "github_repo_id", name="uq_repositories_user_github_repo"),
    )
    op.create_index("ix_repositories_user_id_pushed_at", "repositories", ["user_id", "pushed_at"])

    op.create_table(
        "repo_analyses",
        _uuid_pk(),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_level", sa.String(length=2), nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("batch_position", sa.SmallInteger(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tech_stack", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("notable_areas", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.SmallInteger(), server_default="1", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_repo_analyses"),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_repo_analyses_repository_id_repositories",
            ondelete="CASCADE",
        ),
        # 자연 멱등 키. model 은 넣지 않는다.
        sa.UniqueConstraint(
            "repository_id",
            "analysis_level",
            "head_sha",
            "prompt_version",
            name="uq_repo_analyses_repo_level_sha_prompt",
        ),
        sa.CheckConstraint("analysis_level IN ('l1', 'l2')", name="ck_repo_analyses_level"),
        sa.CheckConstraint(
            "status IN ('succeeded', 'partial', 'failed')", name="ck_repo_analyses_status"
        ),
    )

    op.create_table(
        "user_profile_summaries",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 정렬해서 저장한다 — 재생성 판정 키다.
        sa.Column(
            "based_repo_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("based_on_repo_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("languages", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "project_types", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("role_summary", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_user_profile_summaries"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_profile_summaries_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_user_profile_summaries_user_id"),
    )


def _create_posting_tables() -> None:
    """job_postings, jd_requirements."""
    op.create_table(
        "job_postings",
        _uuid_pk(),
        sa.Column("source", sa.String(length=20), server_default="wanted", nullable=False),
        sa.Column("source_posting_id", sa.Text(), nullable=True),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("domain_category", sa.String(length=20), nullable=True),
        sa.Column("skill_tags", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("parse_status", sa.String(length=20), nullable=False),
        sa.Column("parse_error_code", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_job_postings"),
        sa.UniqueConstraint("normalized_url", name="uq_job_postings_normalized_url"),
        sa.CheckConstraint("source IN ('wanted')", name="ck_job_postings_source"),
        sa.CheckConstraint(
            "parse_status IN ('succeeded', 'partial', 'failed')",
            name="ck_job_postings_parse_status",
        ),
        sa.CheckConstraint(
            "domain_category IN "
            "('finance', 'game', 'travel', 'shopping', 'medical', 'mobility', 'etc')"
            " OR domain_category IS NULL",
            name="ck_job_postings_domain_category",
        ),
    )

    op.create_table(
        "jd_requirements",
        _uuid_pk(),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("tech_tags", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_jd_requirements"),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            name="fk_jd_requirements_job_posting_id_job_postings",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "job_posting_id", "display_order", name="uq_jd_requirements_posting_order"
        ),
        # openapi JdCategory 를 따른다 (팀 결정 2026-09-21).
        sa.CheckConstraint(
            "category IN ('required', 'preferred', 'responsibility')",
            name="ck_jd_requirements_category",
        ),
    )
    op.create_index("ix_jd_requirements_job_posting_id", "jd_requirements", ["job_posting_id"])


def _create_document_tables() -> None:
    """user_documents, document_claims."""
    op.create_table(
        "user_documents",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(length=20), server_default="portfolio", nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        # 파일 바이너리는 저장하지 않는다.
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "extracted_github_urls",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("extract_status", sa.String(length=20), nullable=False),
        sa.Column("extract_error_code", sa.Text(), nullable=True),
        sa.Column("is_truncated", sa.Boolean(), server_default="false", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_user_documents"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_documents_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "doc_type IN ('portfolio', 'cover_letter')", name="ck_user_documents_doc_type"
        ),
        sa.CheckConstraint(
            "extract_status IN ('succeeded', 'partial', 'failed')",
            name="ck_user_documents_extract_status",
        ),
    )
    op.create_index("ix_user_documents_user_id", "user_documents", ["user_id"])

    # Sprint 1 은 테이블만 만들고 row 를 만들지 않는다.
    op.create_table(
        "document_claims",
        _uuid_pk(),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=True),
        sa.Column("tech_tags", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("paragraph_no", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_document_claims"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name="fk_document_claims_document_id_user_documents",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_document_claims_document_id", "document_claims", ["document_id"])


def _create_analysis_tables() -> None:
    """analysis_jobs, analysis_repo_candidates, analysis_repo_candidate_pages, repo_match_scores."""
    op.create_table(
        "analysis_jobs",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("posting_url", sa.Text(), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("steps", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("estimated_seconds", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("queue_wait_ms", sa.Integer(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_jobs"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_analysis_jobs_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            name="fk_analysis_jobs_job_posting_id_job_postings",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name="fk_analysis_jobs_document_id_user_documents",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "job_type IN "
            "('initial_sync', 'analysis_run', 'candidate_page_analyze', 'interview_prep')",
            name="ck_analysis_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'canceled')",
            name="ck_analysis_jobs_status",
        ),
    )
    # 사용자·job_type 당 살아 있는 job 1개 (run_in_progress 의 근거).
    op.create_index(
        "uq_analysis_jobs_active_user_job_type",
        "analysis_jobs",
        ["user_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_analysis_jobs_user_id_created_at", "analysis_jobs", ["user_id", "created_at"]
    )
    op.create_index("ix_analysis_jobs_fingerprint", "analysis_jobs", ["fingerprint"])

    op.create_table(
        "analysis_repo_candidates",
        _uuid_pk(),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_rank", sa.Integer(), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=True),
        sa.Column("batch_rank", sa.Integer(), nullable=True),
        sa.Column("selection_reason", sa.String(length=30), nullable=True),
        sa.Column("ranking_score", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("ranking_signals", postgresql.JSONB(), nullable=True),
        sa.Column("filter_status", sa.String(length=20), nullable=False),
        sa.Column("filter_reason", sa.String(length=20), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_repo_candidates"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_analysis_repo_candidates_analysis_job_id_analysis_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_analysis_repo_candidates_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "repository_id", name="uq_candidates_job_repo"),
        sa.UniqueConstraint("analysis_job_id", "base_rank", name="uq_candidates_job_base_rank"),
        sa.CheckConstraint(
            "filter_status IN ('eligible', 'excluded')",
            name="ck_analysis_repo_candidates_filter_status",
        ),
        sa.CheckConstraint(
            "filter_reason IN "
            "('private', 'fork', 'archived', 'no_language', 'too_small', 'inaccessible')"
            " OR filter_reason IS NULL",
            name="ck_analysis_repo_candidates_filter_reason",
        ),
        sa.CheckConstraint(
            "selection_reason IN "
            "('portfolio_mentioned', 'base_rank_top', 'high_contribution', 'other')"
            " OR selection_reason IS NULL",
            name="ck_analysis_repo_candidates_selection_reason",
        ),
    )
    op.create_index(
        "ix_candidates_job_batch",
        "analysis_repo_candidates",
        ["analysis_job_id", "batch_no", "batch_rank"],
    )

    op.create_table(
        "analysis_repo_candidate_pages",
        _uuid_pk(),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_repo_candidate_pages"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_analysis_repo_candidate_pages_analysis_job_id_analysis_jobs",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "page_no", name="uq_candidate_pages_job_page"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_analysis_repo_candidate_pages_status",
        ),
    )

    op.create_table(
        "repo_match_scores",
        _uuid_pk(),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "matched_requirement_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("recommend_reason", sa.Text(), nullable=True),
        sa.Column("is_recommended", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("candidate_source", sa.String(length=20), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_repo_match_scores"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_repo_match_scores_analysis_job_id_analysis_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_repo_match_scores_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "repository_id", name="uq_match_scores_job_repo"),
        sa.CheckConstraint(
            "candidate_source IN ('rule_filter', 'portfolio', 'both')",
            name="ck_repo_match_scores_candidate_source",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_repo_match_scores_score_range"),
    )


def _create_interview_tables() -> None:
    """interview_sessions, session_repositories, interview_turns."""
    op.create_table(
        "interview_sessions",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retry_of_interview_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="preparing", nullable=False),
        sa.Column("answer_mode", sa.String(length=10), server_default="text", nullable=False),
        sa.Column("total_turns", sa.SmallInteger(), server_default="9", nullable=False),
        sa.Column("current_turn", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("context_state", postgresql.JSONB(), nullable=True),
        sa.Column("prepare_steps", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at_turn", sa.SmallInteger(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_interview_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_interview_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_interview_sessions_analysis_job_id_analysis_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            name="fk_interview_sessions_job_posting_id_job_postings",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_interview_id"],
            ["interview_sessions.id"],
            name="fk_interview_sessions_retry_of_interview_id_interview_sessions",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('preparing', 'preparing_failed', 'in_progress', 'completed', 'abandoned')",
            name="ck_interview_sessions_status",
        ),
        sa.CheckConstraint("answer_mode IN ('text')", name="ck_interview_sessions_answer_mode"),
    )
    # run 당 활성 면접 1개 (session_limit_exceeded 의 근거).
    op.create_index(
        "uq_interview_sessions_active_per_run",
        "interview_sessions",
        ["analysis_job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('preparing', 'in_progress')"),
    )
    op.create_index(
        "ix_interview_sessions_user_id_created_at",
        "interview_sessions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "session_repositories",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        # 값 집합은 task-17 에서 확정한다 — 아직 CHECK 를 걸지 않는다.
        sa.Column("selection_source", sa.String(length=20), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_session_repositories"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name="fk_session_repositories_interview_session_id_interview_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_session_repositories_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "interview_session_id",
            "repository_id",
            name="uq_session_repositories_session_repo",
        ),
    )

    op.create_table(
        "interview_turns",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_no", sa.SmallInteger(), nullable=False),
        sa.Column("persona", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="asked", nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("depth", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("parent_turn_no", sa.SmallInteger(), nullable=True),
        # Sprint 1 은 FK 를 걸지 않는다 (topic_taxonomy 확정 후 Sprint 2).
        sa.Column("topic_code", sa.String(length=50), nullable=True),
        sa.Column(
            "jd_requirement_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "claim_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("analysis", postgresql.JSONB(), nullable=True),
        sa.Column("decision", postgresql.JSONB(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer_duration_sec", sa.Integer(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_interview_turns"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name="fk_interview_turns_interview_session_id_interview_sessions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "interview_session_id", "turn_no", name="uq_interview_turns_session_turn"
        ),
        sa.CheckConstraint(
            "persona IN ('tech_lead', 'hr_manager', 'domain_lead')",
            name="ck_interview_turns_persona",
        ),
        sa.CheckConstraint("status IN ('asked', 'answered')", name="ck_interview_turns_status"),
    )


def _create_evidence_tables() -> None:
    """evidences, turn_evidences, evidence_conflicts."""
    op.create_table(
        "evidences",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        # NOT NULL — 없으면 같은 근거를 다시 꺼낼 수 없다.
        sa.Column("git_ref", sa.String(length=40), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=50), nullable=True),
        sa.Column("retrieved_for_turn", sa.SmallInteger(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_evidences"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name="fk_evidences_interview_session_id_interview_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_evidences_repository_id_repositories",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "source_type IN ('readme', 'repo_metadata', 'languages', 'commit', 'file')",
            name="ck_evidences_source",
        ),
    )
    op.create_index("ix_evidences_session_id", "evidences", ["interview_session_id"])

    # PK 에 usage 가 들어간다 — 같은 evidence 가 질문 근거이면서 채점 근거일 수 있다.
    op.create_table(
        "turn_evidences",
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage", sa.String(length=20), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("turn_id", "evidence_id", "usage", name="pk_turn_evidences"),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["interview_turns.id"],
            name="fk_turn_evidences_turn_id_interview_turns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidences.id"],
            name="fk_turn_evidences_evidence_id_evidences",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "usage IN ('question_basis', 'evaluation_basis')", name="ck_turn_evidences_usage"
        ),
    )

    # Sprint 1 은 테이블만 만들고 행을 만들지 않는다.
    op.create_table(
        "evidence_conflicts",
        _uuid_pk(),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        # FK 없이 둔다. Sprint 2 에서 document_claims FK 를 추가한다.
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=30), server_default="answer_vs_code", nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=20), server_default="unresolved", nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_conflicts"),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["interview_turns.id"],
            name="fk_evidence_conflicts_turn_id_interview_turns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidences.id"],
            name="fk_evidence_conflicts_evidence_id_evidences",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("source IN ('answer_vs_code')", name="ck_evidence_conflicts_source"),
        sa.CheckConstraint("verdict IN ('unresolved')", name="ck_evidence_conflicts_verdict"),
    )
    op.create_index("ix_evidence_conflicts_turn_id", "evidence_conflicts", ["turn_id"])


def _create_report_tables() -> None:
    """interview_reports, report_scores, report_disagreements."""
    op.create_table(
        "interview_reports",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=5, scale=2), nullable=False),
        # persona 별 피드백. report_persona_feedbacks 테이블은 만들지 않는다.
        sa.Column("feedback_json", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("coverage_json", postgresql.JSONB(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_interview_reports"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name="fk_interview_reports_interview_session_id_interview_sessions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "interview_session_id", name="uq_interview_reports_interview_session_id"
        ),
        sa.CheckConstraint(
            "total_score >= 0 AND total_score <= 100", name="ck_interview_reports_total"
        ),
    )

    op.create_table(
        "report_scores",
        _uuid_pk(),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_key", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence_turn_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default="{}",
            nullable=False,
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_report_scores"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["interview_reports.id"],
            name="fk_report_scores_report_id_interview_reports",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("report_id", "score_key", name="uq_report_scores_report_key"),
        sa.CheckConstraint(
            "score_key IN "
            "('project_understanding', 'technical_reasoning', 'problem_solving', "
            "'communication', 'contribution_clarity', 'company_job_fit')",
            name="ck_report_scores_key",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_report_scores_range"),
    )

    # Sprint 1 은 테이블만 만들고 API·row 생성은 Sprint 2 다.
    op.create_table(
        "report_disagreements",
        _uuid_pk(),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("persona", sa.String(length=20), nullable=False),
        sa.Column("reason_type", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_report_disagreements"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["interview_reports.id"],
            name="fk_report_disagreements_report_id_interview_reports",
            ondelete="CASCADE",
        ),
        # persona 당 1회 — Sprint 2 의 already_submitted 근거.
        sa.UniqueConstraint("report_id", "persona", name="uq_report_disagreements_report_persona"),
        sa.CheckConstraint(
            "persona IN ('tech_lead', 'hr_manager', 'domain_lead')",
            name="ck_report_disagreements_persona",
        ),
        sa.CheckConstraint(
            "reason_type IN "
            "('factual_error', 'insufficient_basis', 'overly_harsh', 'unclear_intent', 'other')",
            name="ck_report_disagreements_reason_type",
        ),
    )


def _create_knowledge_tables() -> None:
    """score_criteria, prompt_versions, domain_question_frames."""
    op.create_table(
        "score_criteria",
        _uuid_pk(),
        sa.Column("score_key", sa.String(length=30), nullable=False),
        sa.Column("label_ko", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rubric", postgresql.JSONB(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_score_criteria"),
        sa.UniqueConstraint("score_key", name="uq_score_criteria_score_key"),
        sa.CheckConstraint(
            "score_key IN "
            "('project_understanding', 'technical_reasoning', 'problem_solving', "
            "'communication', 'contribution_clarity', 'company_job_fit')",
            name="ck_score_criteria_key",
        ),
    )

    op.create_table(
        "prompt_versions",
        _uuid_pk(),
        sa.Column("task_name", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        # 모델명을 코드 상수로 두지 않고 여기서 읽는다.
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        sa.UniqueConstraint("task_name", "version", name="uq_prompt_versions_task_version"),
    )
    # task 당 활성 버전 1개.
    op.create_index(
        "uq_prompt_versions_active_per_task",
        "prompt_versions",
        ["task_name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "domain_question_frames",
        _uuid_pk(),
        sa.Column("domain_category", sa.String(length=20), nullable=False),
        sa.Column("axis", sa.String(length=40), nullable=False),
        sa.Column("frame_text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_domain_question_frames"),
        sa.UniqueConstraint(
            "domain_category",
            "axis",
            "display_order",
            name="uq_domain_frames_category_axis_order",
        ),
        sa.CheckConstraint(
            "domain_category IN "
            "('finance', 'game', 'travel', 'shopping', 'medical', 'mobility', 'etc')",
            name="ck_domain_question_frames_category",
        ),
        sa.CheckConstraint(
            "axis IN "
            "('privacy_sensitive_data', 'reliability_operations', 'user_experience_context')",
            name="ck_domain_question_frames_axis",
        ),
    )


def _create_metric_tables() -> None:
    """events. task-17 이 고정한 10종 event_name 만 허용한다."""
    op.create_table(
        "events",
        _uuid_pk(),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        # 이벤트 기록 실패가 핵심 트랜잭션을 실패시키지 않도록 전부 nullable + SET NULL.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_events_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_events_analysis_job_id_analysis_jobs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name="fk_events_interview_session_id_interview_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_events_repository_id_repositories",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "event_name IN "
            "('analysis_run_started', 'analysis_run_completed', 'analysis_run_failed', "
            "'repo_recommended', 'repo_selected', 'interview_started', 'turn_asked', "
            "'turn_answered', 'interview_completed', 'report_viewed')",
            name="ck_events_event_name",
        ),
    )
    op.create_index("ix_events_event_name_created_at", "events", ["event_name", "created_at"])
    op.create_index("ix_events_user_id_created_at", "events", ["user_id", "created_at"])


def upgrade() -> None:
    # UUID PK 기본값 gen_random_uuid() 가 이 extension 을 요구한다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _create_account_tables()
    _create_github_tables()
    _create_posting_tables()
    _create_document_tables()
    _create_analysis_tables()
    _create_interview_tables()
    _create_evidence_tables()
    _create_report_tables()
    _create_knowledge_tables()
    _create_metric_tables()


def downgrade() -> None:
    for table in reversed(_TABLES_IN_CREATE_ORDER):
        op.drop_table(table)
    # extension 은 다른 스키마가 쓸 수 있으므로 되돌리지 않는다.
