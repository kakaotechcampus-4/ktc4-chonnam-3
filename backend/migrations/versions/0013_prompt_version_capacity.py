"""배포 식별자를 포함한 prompt version을 자르지 않고 보존한다."""

import sqlalchemy as sa
from alembic import op

revision = "0013_prompt_version_capacity"
down_revision = "0012_profile_refresh_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "prompt_versions",
        "version",
        existing_type=sa.String(20),
        type_=sa.String(100),
        existing_nullable=False,
    )


def downgrade():
    # 검사 뒤 긴 버전이 동시 INSERT되는 경합도 막는다. 활성·비활성 이력을 모두 보존한다.
    op.execute(sa.text("LOCK TABLE prompt_versions IN ACCESS EXCLUSIVE MODE"))
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM prompt_versions WHERE char_length(version) > 20)")
    ):
        raise RuntimeError("Prompt versions must be preserved before downgrade")
    op.alter_column(
        "prompt_versions",
        "version",
        existing_type=sa.String(100),
        type_=sa.String(20),
        existing_nullable=False,
    )
