"""문서 Claim 예약의 실제 작성자가 정한 만료 시각을 보존한다."""

import sqlalchemy as sa
from alembic import op

revision = "0018_document_claim_lease"
down_revision = "0017_profile_generation_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_documents", sa.Column("claims_lease_expires_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    # 실행 중인 예약의 유효기간을 없애면 짧은 대기자가 소유권을 잘못 넘겨받을 수 있다.
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM user_documents "
            "WHERE claims_status='running' AND claims_lease_expires_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Finish active document claim reservations before downgrade")
    op.drop_column("user_documents", "claims_lease_expires_at")
