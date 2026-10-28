"""알림 장애와 필수 worker 설정 누락을 구분한다."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.features.analysis.pipeline.run_state import notify


async def test_missing_worker_settings_fails_before_opening_redis_pipeline():
    redis = Mock()

    with pytest.raises(KeyError, match="settings"):
        await notify({"redis": redis}, uuid4(), {"type": "completed"}, {})

    redis.pipeline.assert_not_called()
