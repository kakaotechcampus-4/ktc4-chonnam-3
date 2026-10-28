"""질문 계약, 고정 코드 ref, Evidence 출처와 면접 모델 호출 기록을 보존한다.

Revision ID: 0002_agent_storage
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_agent_storage"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 질문의 계약·선택 당시 SHA는 추측하여 backfill하지 않는다.
    op.add_column(
        "interview_turns", sa.Column("question_contract", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "session_repositories", sa.Column("snapshot_head_sha", sa.String(40), nullable=True)
    )
    op.add_column("evidences", sa.Column("metadata_key", sa.Text(), nullable=True))
    op.add_column("evidences", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("evidences", sa.Column("start_line", sa.Integer(), nullable=True))
    op.add_column("evidences", sa.Column("end_line", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_evidences_line_range"),
        "evidences",
        "(start_line IS NULL AND end_line IS NULL) OR "
        "(start_line IS NOT NULL AND end_line IS NOT NULL "
        "AND start_line > 0 AND end_line >= start_line "
        "AND path IS NOT NULL AND metadata_key IS NULL)",
    )
    op.create_table(
        "llm_call_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("turn_no", sa.SmallInteger(), nullable=True),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("attempts", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("failure", postgresql.JSONB(), nullable=True),
        sa.Column("discard_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call_records")),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name=op.f("fk_llm_call_records_interview_session_id_interview_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["interview_turns.id"],
            name=op.f("fk_llm_call_records_turn_id_interview_turns"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_llm_call_records_interview_session_id_created_at",
        "llm_call_records",
        ["interview_session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("llm_call_records")
    op.drop_constraint(op.f("ck_evidences_line_range"), "evidences", type_="check")
    for name in ("end_line", "start_line", "summary", "metadata_key"):
        op.drop_column("evidences", name)
    op.drop_column("session_repositories", "snapshot_head_sha")
    op.drop_column("interview_turns", "question_contract")
