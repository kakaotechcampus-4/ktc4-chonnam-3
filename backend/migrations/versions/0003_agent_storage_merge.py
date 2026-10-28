"""기존 Agent 저장과 공고 버전 revision을 DDL 없이 합친다."""

revision = "0003_agent_storage_merge"
down_revision = ("0002_agent_storage", "0002_posting_versions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 두 부모의 기존 DDL을 다시 실행하거나 이미 적용된 revision을 재작성하지 않는다.
    pass


def downgrade() -> None:
    # 합류 revision만 되돌리므로 두 부모가 만든 자료와 스키마는 유지한다.
    pass
