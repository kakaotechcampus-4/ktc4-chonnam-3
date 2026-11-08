"""이미지 공고의 요구사항을 실제 전사 블록에 연결한다."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_jd_image_sources"
down_revision = "0008_document_claim_comparison"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jd_requirements",
        sa.Column(
            "source_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("jd_requirements", "source_refs")
