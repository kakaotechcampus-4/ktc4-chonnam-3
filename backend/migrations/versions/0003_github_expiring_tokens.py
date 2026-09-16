"""Support expiring GitHub tokens without discarding existing accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL metadata identifies pre-migration non-expiring tokens until next login.
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
    # Old code must not mistake an expiring token for a non-expiring credential.
    op.execute(
        "UPDATE github_accounts SET token_status = 'revoked' WHERE token_expires_at IS NOT NULL"
    )
    op.drop_constraint("ck_github_accounts_token_pair", "github_accounts", type_="check")
    op.drop_column("github_accounts", "refresh_token_expires_at")
    op.drop_column("github_accounts", "refresh_token_encrypted")
    op.drop_column("github_accounts", "token_expires_at")
