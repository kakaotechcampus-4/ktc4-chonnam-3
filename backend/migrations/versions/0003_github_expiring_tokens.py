"""기존 계정을 보존하면서 만료형 GitHub 토큰을 지원한다."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 다음 로그인 전까지는 NULL 메타데이터로 기존 비만료 토큰을 구분한다.
    op.add_column("github_accounts", sa.Column("token_expires_at", sa.DateTime(timezone=True)))
    op.add_column("github_accounts", sa.Column("refresh_token_encrypted", sa.LargeBinary()))
    op.add_column(
        "github_accounts", sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True))
    )
    op.create_check_constraint(
        "ck_github_accounts_token_pair",
        "github_accounts",
        "(token_expires_at IS NULL AND refresh_token_encrypted IS NULL "
        "AND refresh_token_expires_at IS NULL) OR "
        "(token_expires_at IS NOT NULL AND refresh_token_encrypted IS NOT NULL "
        "AND refresh_token_expires_at IS NOT NULL)",
    )


def downgrade() -> None:
    # 구버전 코드가 만료형 토큰을 비만료 토큰으로 오인하지 않도록 한다.
    op.execute(
        "UPDATE github_accounts SET token_status = 'revoked' WHERE token_expires_at IS NOT NULL"
    )
    op.drop_constraint("ck_github_accounts_token_pair", "github_accounts", type_="check")
    op.drop_column("github_accounts", "refresh_token_expires_at")
    op.drop_column("github_accounts", "refresh_token_encrypted")
    op.drop_column("github_accounts", "token_expires_at")
