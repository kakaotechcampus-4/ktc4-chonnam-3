"""now() 주입 - 테스트에서 시간 고정.

docs/layer-rules.md 1절 / task-04
"""

from datetime import UTC, datetime


def now() -> datetime:
    """UTC aware 현재 시각. DB 의 timestamptz 와 짝을 맞춘다."""
    return datetime.now(UTC)
