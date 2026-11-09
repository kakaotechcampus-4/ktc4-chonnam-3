"""프로필 마지막 실제 생성의 task 상한을 보존한다."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0011_profile_generation_limits"
down_revision = "0010_report_review_runtime"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_profile_summaries", sa.Column("generation_limits", pg.JSONB(), nullable=True)
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM user_profile_summaries "
            "WHERE generation_limits IS NOT NULL)"
        )
    ):
        raise RuntimeError("Profile generation audit must be preserved before downgrade")
    op.drop_column("user_profile_summaries", "generation_limits")
