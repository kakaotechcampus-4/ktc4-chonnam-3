"""분석 단계의 선행 합류와 기존 Director 합류를 이력 변경 없이 연결한다.

#82 다음 #108 단계도 단일 head여야 하므로 그 합류 revision을 다시 부모로 연결한다.
기존 revision의 ID·부모·DDL은 보존하며 이 revision 자체에는 DDL이 없다.
"""

revision = "0005_director_foundation_merge"
down_revision = (
    "0004_analysis_storage_merge",
    "0004_interview_foundation_merge",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
