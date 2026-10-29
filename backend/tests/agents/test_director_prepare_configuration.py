"""LLM 필수 설정 오류는 외부 호출 없이 비재시도 실패로 저장한다."""

import httpx
import pytest

from app.core.config import Settings
from app.db.models import InterviewSession
from app.features.interview import prepare
from tests.agents.test_director_prepare import ready as ready


@pytest.mark.parametrize("proxy", [False, True])
async def test_configuration_failure_is_nonrecoverable_without_io(agent_sessions, ready, proxy):
    settings = Settings(_env_file=None, proxy_token="fixture" if proxy else None)

    async def unexpected(request):
        raise AssertionError("설정 실패 뒤 외부 요청을 보내면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        result = await prepare.prepare_interview(
            agent_sessions,
            user_id=ready["owner"],
            interview_id=ready["interview_id"],
            settings=settings,
            http_client=http,
        )
    assert result is False
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.status == "preparing_failed"
        assert row.last_error["code"] == "llm_config_unavailable"
        assert row.last_error["recoverable"] is False
        assert "prepare_job_id" not in row.context_state
