"""공고 고정 버전과 Director 저장 경계의 독립 migration head를 연결한다.

기존 두 revision과 자료를 바꾸지 않고 공통 후속 실행 지점을 만든다.
"""

revision = "0003_director_runtime"
down_revision = ("0002_agent_storage", "0002_posting_versions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
