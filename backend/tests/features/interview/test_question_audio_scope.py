"""리뷰에서 확인한 호출 범위의 회귀 검사."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.features.interview.question_audio import load_question


@pytest.mark.parametrize(
    "mode,status,current",
    [
        ("text", "in_progress", 1),
        ("voice", "completed", 1),
        ("voice", "abandoned", 1),
        ("voice", "in_progress", 2),
    ],
)
async def test_audio_rejects_noncurrent_voice_scope_before_reading_text(mode, status, current):
    owner, interview = uuid4(), uuid4()
    db = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                user_id=owner, answer_mode=mode, status=status, current_turn=current
            )
        ),
        scalar=AsyncMock(),
    )
    with pytest.raises(AppError):
        await load_question(db, user_id=owner, interview_id=interview, turn_no=1)
    db.scalar.assert_not_awaited()
