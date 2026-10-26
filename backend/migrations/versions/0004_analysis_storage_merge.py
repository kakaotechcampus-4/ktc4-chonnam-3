"""기존 저장·분석 migration 이력을 보존하는 DDL 없는 합류 지점."""

revision = "0004_analysis_storage_merge"
down_revision = ("0003_agent_storage_merge", "0003_analysis_runs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
