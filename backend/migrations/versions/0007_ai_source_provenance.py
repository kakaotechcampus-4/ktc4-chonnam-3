"""문서 추출 원문·Claim 위치와 면접별 외부 자료를 코드 근거와 분리해 보존한다."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_ai_source_provenance"
# #185의 음성 DB 변경과 독립된 현재 게시본은 기존 합류 지점에서 시작한다.
down_revision = "0005_director_foundation_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column("cover_letter_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_analysis_jobs_cover_letter_document_id_user_documents",
        "analysis_jobs",
        "user_documents",
        ["cover_letter_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("user_documents", sa.Column("source_snapshot", postgresql.JSONB(), nullable=True))
    op.add_column(
        "user_documents",
        sa.Column("claims_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("user_documents", sa.Column("claims_error_code", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_user_documents_claims_status"),
        "user_documents",
        "claims_status IN ('pending', 'running', 'succeeded', 'failed', 'not_available')",
    )
    op.add_column(
        "user_documents", sa.Column("claims_active_ids", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "user_documents", sa.Column("claims_run_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "user_documents", sa.Column("claims_prompt_version", sa.String(100), nullable=True)
    )
    op.add_column(
        "user_documents", sa.Column("claims_source_version", sa.String(64), nullable=True)
    )
    op.add_column("document_claims", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column(
        "document_claims", sa.Column("source_location", postgresql.JSONB(), nullable=True)
    )
    op.add_column("document_claims", sa.Column("source_version", sa.String(64), nullable=True))
    op.create_table(
        "interview_external_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_scope", sa.String(30), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("limitations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id", name="pk_interview_external_sources"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "interview_session_id", "url", "content_hash", name="uq_external_source"
        ),
        sa.CheckConstraint(
            "content_scope IN ('search_snippet', 'extracted_page')",
            name="ck_interview_external_sources_content_scope",
        ),
    )
    op.create_index(
        "ix_external_sources_interview", "interview_external_sources", ["interview_session_id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_user_documents_claims_status"), "user_documents", type_="check")
    op.drop_constraint(
        "fk_analysis_jobs_cover_letter_document_id_user_documents",
        "analysis_jobs",
        type_="foreignkey",
    )
    op.drop_column("analysis_jobs", "cover_letter_document_id")
    op.drop_table("interview_external_sources")
    for name in ("source_version", "source_location", "source_text"):
        op.drop_column("document_claims", name)
    for name in (
        "claims_active_ids",
        "claims_run_id",
        "claims_prompt_version",
        "claims_source_version",
        "claims_error_code",
        "claims_status",
        "source_snapshot",
    ):
        op.drop_column("user_documents", name)
