"""0001 · 분석 run 범위 초기 스키마 (수동 작성).

이번 범위(공고 입력 · repo 수집 · 진행률 폴링)에 필요한 테이블만 만든다.
면접/근거/리포트/지식/지표 테이블은 task-02 에서 이어서 추가한다.

- PK 는 UUID DEFAULT gen_random_uuid() (pgcrypto 필요)
- PostgreSQL ENUM 금지 -> VARCHAR + CHECK
- JSON 은 JSONB, 배열은 TEXT[]/UUID[]

Revision ID: 0001_analysis_core
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_analysis_core"
down_revision = None
branch_labels = None
depends_on = None

_UUID_PK = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("status", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.CheckConstraint(
            "status IN ('active','suspended','withdrawn')", name="ck_users_users_status"
        ),
    )

    op.create_table(
        "github_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("token_status", sa.String(20), server_default=sa.text("'valid'"), nullable=False),
        sa.Column("token_scope", sa.String(200)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_github_accounts"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_github_accounts_user_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", name="uq_github_accounts_user_id"),
        sa.UniqueConstraint("github_user_id", name="uq_github_accounts_github_user_id"),
        sa.CheckConstraint(
            "token_status IN ('valid','revoked')",
            name="ck_github_accounts_github_accounts_token_status",
        ),
    )

    op.create_table(
        "user_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("extract_status", sa.String(20), nullable=False),
        sa.Column("extracted_text", sa.Text()),
        sa.Column(
            "extracted_github_urls",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("failure_reason", sa.String(50)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_user_documents"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_documents_user_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "extract_status IN ('succeeded','partial','failed')",
            name="ck_user_documents_user_documents_extract_status",
        ),
    )
    op.create_index("ix_user_documents_user", "user_documents", ["user_id"])

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("html_url", sa.String(500), nullable=False),
        sa.Column("default_branch", sa.String(200)),
        sa.Column("primary_language", sa.String(100)),
        sa.Column(
            "topics", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("stars", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("forks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("size_kb", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_fork", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("repo_created_at", sa.DateTime(timezone=True)),
        sa.Column("repo_pushed_at", sa.DateTime(timezone=True)),
        sa.Column("languages", postgresql.JSONB()),
        sa.Column("readme_text", sa.Text()),
        sa.Column(
            "readme_truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("head_sha", sa.String(40)),
        sa.Column("commit_count", sa.Integer()),
        sa.Column("user_commit_count", sa.Integer()),
        sa.Column("fetch_level", sa.String(20), server_default=sa.text("'list'"), nullable=False),
        sa.Column("fetch_error_code", sa.String(50)),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_repositories"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_repositories_user_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "github_repo_id", name="uq_repositories_user_github_repo"),
        sa.UniqueConstraint("user_id", "full_name", name="uq_repositories_user_full_name"),
        sa.CheckConstraint(
            "fetch_level IN ('list','detail')", name="ck_repositories_repositories_fetch_level"
        ),
    )
    op.create_index("ix_repositories_user_pushed_at", "repositories", ["user_id", "repo_pushed_at"])

    op.create_table(
        "repo_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_level", sa.String(20), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("summary", sa.Text()),
        sa.Column("tech_stack", postgresql.ARRAY(sa.Text())),
        sa.Column("notable_areas", postgresql.JSONB()),
        sa.Column("raw_output", postgresql.JSONB()),
        sa.Column("batch_position", sa.SmallInteger()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_repo_analyses"),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_repo_analyses_repository_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "repository_id",
            "analysis_level",
            "head_sha",
            "prompt_version",
            name="uq_repo_analyses_cache_key",
        ),
        sa.CheckConstraint(
            "analysis_level IN ('shallow','deep')", name="ck_repo_analyses_repo_analyses_level"
        ),
        sa.CheckConstraint(
            "status IN ('succeeded','partial','failed')",
            name="ck_repo_analyses_repo_analyses_status",
        ),
    )

    op.create_table(
        "job_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("normalized_url", sa.String(1000), nullable=False),
        sa.Column("site_adapter", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(100)),
        sa.Column("position", sa.String(300)),
        sa.Column("company_name", sa.String(300)),
        sa.Column("content_form", sa.String(20), server_default=sa.text("'text'"), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("raw_json", postgresql.JSONB()),
        sa.Column(
            "source_image_urls",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "skill_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("parse_status", sa.String(20), nullable=False),
        sa.Column("parse_error_code", sa.String(50)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_job_postings"),
        sa.UniqueConstraint("normalized_url", name="uq_job_postings_normalized_url"),
        sa.CheckConstraint(
            "parse_status IN ('success','failed')",
            name="ck_job_postings_job_postings_parse_status",
        ),
        sa.CheckConstraint(
            "content_form IN ('text','image')",
            name="ck_job_postings_job_postings_content_form",
        ),
    )

    op.create_table(
        "jd_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_type", sa.String(20), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column(
            "tech_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jd_requirements"),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            name="fk_jd_requirements_job_posting_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "requirement_type IN ('required','preferred','unknown')",
            name="ck_jd_requirements_jd_requirements_type",
        ),
    )
    op.create_index(
        "ix_jd_requirements_posting_order",
        "jd_requirements",
        ["job_posting_id", "display_order"],
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("posting_url", sa.String(1000)),
        sa.Column("normalized_posting_url", sa.String(1000)),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "steps", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("progress", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_jobs"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_analysis_jobs_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            name="fk_analysis_jobs_job_posting_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name="fk_analysis_jobs_document_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "job_type IN ('initial_sync','analysis_run','interview_prep','deep_analysis')",
            name="ck_analysis_jobs_analysis_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','partial','failed','canceled')",
            name="ck_analysis_jobs_analysis_jobs_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_analysis_jobs_analysis_jobs_progress"
        ),
    )
    # 사용자당 job_type 별 동시 실행 1개 (queued/running 일 때만).
    op.create_index(
        "uq_analysis_jobs_active_per_type",
        "analysis_jobs",
        ["user_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_index(
        "ix_analysis_jobs_user_fingerprint", "analysis_jobs", ["user_id", "fingerprint"]
    )

    op.create_table(
        "analysis_repo_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_rank", sa.Integer(), nullable=False),
        sa.Column("batch_no", sa.SmallInteger()),
        sa.Column("batch_rank", sa.SmallInteger()),
        sa.Column("selection_reason", sa.String(30)),
        sa.Column("ranking_score", sa.Numeric(6, 3)),
        sa.Column("ranking_signals", postgresql.JSONB()),
        sa.Column(
            "filter_status", sa.String(20), server_default=sa.text("'eligible'"), nullable=False
        ),
        sa.Column("filter_reason", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_repo_candidates"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_analysis_repo_candidates_analysis_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_analysis_repo_candidates_repository_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "repository_id", name="uq_candidates_job_repo"),
        sa.UniqueConstraint("analysis_job_id", "base_rank", name="uq_candidates_job_base_rank"),
        sa.CheckConstraint(
            "selection_reason IN "
            "('portfolio_mentioned','base_rank_top','jd_signal','high_contribution','other')",
            name="ck_analysis_repo_candidates_candidates_selection_reason",
        ),
        sa.CheckConstraint(
            "filter_status IN ('eligible','excluded')",
            name="ck_analysis_repo_candidates_candidates_filter_status",
        ),
        sa.CheckConstraint(
            "filter_reason IS NULL OR filter_reason IN "
            "('private','fork','archived','no_language','too_small','inaccessible')",
            name="ck_analysis_repo_candidates_candidates_filter_reason",
        ),
    )
    op.create_index(
        "ix_candidates_job_batch",
        "analysis_repo_candidates",
        ["analysis_job_id", "batch_no", "batch_rank"],
    )

    op.create_table(
        "analysis_repo_candidate_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_no", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_repo_candidate_pages"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_analysis_repo_candidate_pages_analysis_job_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "page_no", name="uq_candidate_pages_job_page"),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed')",
            name="ck_analysis_repo_candidate_pages_candidate_pages_status",
        ),
    )

    op.create_table(
        "repo_match_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=_UUID_PK, nullable=False),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_score", sa.Numeric(6, 2)),
        sa.Column(
            "matched_requirement_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("recommend_reason", sa.Text()),
        sa.Column(
            "is_ai_recommended", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_repo_match_scores"),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_repo_match_scores_analysis_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_repo_match_scores_repository_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("analysis_job_id", "repository_id", name="uq_match_scores_job_repo"),
    )


def downgrade() -> None:
    """이 revision 이 만든 테이블만 되돌린다. pgcrypto 는 남긴다."""
    op.drop_table("repo_match_scores")
    op.drop_table("analysis_repo_candidate_pages")
    op.drop_index("ix_candidates_job_batch", table_name="analysis_repo_candidates")
    op.drop_table("analysis_repo_candidates")
    op.drop_index("ix_analysis_jobs_user_fingerprint", table_name="analysis_jobs")
    op.drop_index("uq_analysis_jobs_active_per_type", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_jd_requirements_posting_order", table_name="jd_requirements")
    op.drop_table("jd_requirements")
    op.drop_table("job_postings")
    op.drop_table("repo_analyses")
    op.drop_index("ix_repositories_user_pushed_at", table_name="repositories")
    op.drop_table("repositories")
    op.drop_index("ix_user_documents_user", table_name="user_documents")
    op.drop_table("user_documents")
    op.drop_table("github_accounts")
    op.drop_table("users")
