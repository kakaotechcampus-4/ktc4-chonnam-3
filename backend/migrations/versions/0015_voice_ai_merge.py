"""이미 적용된 음성 입력과 AI 확장 이력을 변경 없이 합류한다."""

revision = "0015_voice_ai_merge"
down_revision = ("0014_official_source_snapshots", "0006_answer_mode_voice")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 두 부모가 각자의 DDL을 적용한다. 합류 지점은 데이터나 스키마를 다시 변경하지 않는다.
    pass


def downgrade() -> None:
    # 합류 표시만 해제한다. 음성 세션과 공식 원문의 보호 조건은 부모 revision이 유지한다.
    pass
