"""Sprint 1 초기 스키마.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-21

수동 작성이다 (task-02). autogenerate 는 참고용으로만 썼다.

downgrade 가능 범위: 이 migration 이 만든 테이블과 pgcrypto extension 전부를 되돌린다.
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
        # 값 집합 미합의 — db-schema.md(unknown) 와 openapi(responsibility) 의 합집합이다.
        sa.CheckConstraint(
            "category IN ('required', 'preferred', 'responsibility', 'unknown')",
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
            "filter_status IN ('eligible', 'excluded')", name="ck_candidates_filter_status"
        ),
        sa.CheckConstraint(
            "filter_reason IN "
            "('private', 'fork', 'archived', 'no_language', 'too_small', 'inaccessible')"
            " OR filter_reason IS NULL",
            name="ck_candidates_filter_reason",
        ),
        sa.CheckConstraint(
            "selection_reason IN "
            "('portfolio_mentioned', 'base_rank_top', 'high_contribution', 'other')"
            " OR selection_reason IS NULL",
            name="ck_candidates_selection_reason",
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
            name="ck_candidate_pages_status",
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
            name="ck_match_scores_candidate_source",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_match_scores_score_range"),
    )


def upgrade() -> None:
    # UUID PK 기본값 gen_random_uuid() 가 이 extension 을 요구한다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _create_account_tables()
    _create_github_tables()
    _create_posting_tables()
    _create_document_tables()
    _create_analysis_tables()


def downgrade() -> None:
    for table in reversed(_TABLES_IN_CREATE_ORDER):
        op.drop_table(table)
    # extension 은 다른 스키마가 쓸 수 있으므로 되돌리지 않는다.
