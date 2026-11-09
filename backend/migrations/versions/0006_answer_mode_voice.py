"""interview_sessions.answer_mode에 voice를 허용하고 새 세션의 기본값을 voice로 바꾼다.

기존 `text` 세션은 그대로 둔다(행을 바꾸지 않는다). CHECK만 `('text','voice')`로 넓히므로
운영 데이터와 무관하게 적용되며, 텍스트 입력을 없애는 결정(0007)은 이후 별도 revision으로 좁힌다.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_answer_mode_voice"
down_revision = "0005_director_foundation_merge"
branch_labels = None
depends_on = None

_CHECK = "ck_interview_sessions_answer_mode"


def upgrade() -> None:
    op.drop_constraint(_CHECK, "interview_sessions", type_="check")
    op.create_check_constraint(_CHECK, "interview_sessions", "answer_mode IN ('text', 'voice')")
    op.alter_column("interview_sessions", "answer_mode", server_default=sa.text("'voice'"))


def downgrade() -> None:
    # voice 세션이 있으면 text로 되돌릴 수 없으므로 먼저 막아 데이터를 잃지 않는다.
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT 1 FROM interview_sessions WHERE answer_mode = 'voice' LIMIT 1")
    ).first():
        raise RuntimeError("voice 면접 세션이 있어 answer_mode를 text로 되돌릴 수 없습니다")
    op.alter_column("interview_sessions", "answer_mode", server_default=sa.text("'text'"))
    op.drop_constraint(_CHECK, "interview_sessions", type_="check")
    op.create_check_constraint(_CHECK, "interview_sessions", "answer_mode IN ('text')")
