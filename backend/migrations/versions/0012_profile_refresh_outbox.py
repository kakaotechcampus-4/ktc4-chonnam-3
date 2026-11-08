"""보고서 성공 뒤 프로필 큐 전달의 영속 복구 기록."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0012_profile_refresh_outbox"
down_revision = "0011_profile_generation_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_refresh_requests",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "report_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("interview_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("owner_token", pg.UUID(as_uuid=True)),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint(
            "report_id", "report_revision", name="uq_profile_refresh_report_revision"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'succeeded', 'failed')", name="status"
        ),
        sa.CheckConstraint("report_revision >= 1", name="revision"),
        sa.CheckConstraint("dispatch_attempts >= 0 AND dispatch_attempts <= 5", name="attempts"),
    )
    op.create_index(
        "ix_profile_refresh_due", "profile_refresh_requests", ["status", "next_attempt_at", "id"]
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM profile_refresh_requests)")):
        raise RuntimeError("Profile delivery audit must be preserved before downgrade")
    op.drop_index("ix_profile_refresh_due", table_name="profile_refresh_requests")
    op.drop_table("profile_refresh_requests")
