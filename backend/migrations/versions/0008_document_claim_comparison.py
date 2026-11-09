"""문서 Claim과 실제 코드 원문의 대조·미확인 결과를 불변 입력별로 보존한다."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_document_claim_comparison"
down_revision = "0007_ai_source_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_claim_comparisons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("claim_source", postgresql.JSONB(), nullable=False),
        sa.Column("code_sources", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("execution_status", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_document_claim_comparisons"),
        sa.ForeignKeyConstraint(
            ["interview_session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["document_claims.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "claim_id", name="uq_claim_comparison_run_claim"),
        sa.CheckConstraint(
            "status IN ('consistent', 'conflicting', 'unverified')",
            name="ck_document_claim_comparisons_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded', 'failed', 'not_available', 'budget_exhausted')",
            name="ck_document_claim_comparisons_execution_status",
        ),
    )
    op.create_index(
        "ix_claim_comparisons_interview", "document_claim_comparisons", ["interview_session_id"]
    )


def downgrade() -> None:
    op.drop_table("document_claim_comparisons")
