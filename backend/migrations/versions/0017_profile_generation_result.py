"""검증된 프로필 생성 결과를 영속 전달의 재시도 동안만 보존한다."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0017_profile_generation_result"
down_revision = "0016_source_check_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profile_refresh_requests", sa.Column("generated_result", pg.JSONB()))


def downgrade() -> None:
    # 아직 재사용할 성공 결과를 조용히 버리는 downgrade는 허용하지 않는다.
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM profile_refresh_requests "
            "WHERE generated_result IS NOT NULL)"
        )
    ):
        raise RuntimeError("Finish pending profile generation results before downgrade")
    op.drop_column("profile_refresh_requests", "generated_result")
