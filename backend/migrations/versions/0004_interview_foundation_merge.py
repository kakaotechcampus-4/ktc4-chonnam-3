"""저장·분석 실행·기존 Director merge 이력을 보존해 단일 후속 지점으로 합친다.

#82와 #108의 선행 revision이 반영된 뒤에 적용한다. 기존 revision의 ID·부모와
DDL은 바꾸지 않으며 이 revision 자체도 업무 테이블을 수정하지 않는다.
"""

revision = "0004_interview_foundation_merge"
down_revision = (
    "0003_agent_storage_merge",
    "0003_director_runtime",
    "0003_analysis_runs",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
