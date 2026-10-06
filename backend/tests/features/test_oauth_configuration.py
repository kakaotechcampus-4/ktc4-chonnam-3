"""A supported provider response can still conflict with the chosen token model."""

import logging

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError, Reason
from app.core.logging import configure_logging
from app.features.auth.oauth import GitHubOAuth


async def test_expiring_token_reports_configuration_error_without_logging_secrets(caplog):
    configure_logging()
    caplog.set_level(logging.WARNING)
    settings = Settings(_env_file=None, github_client_id="test", github_client_secret="test")
    payload = {
        "access_token": "private-access-token-sentinel",
        "token_type": "bearer",
        "scope": "read:user",
        "expires_in": 28800,
        "refresh_token": "private-refresh-token-sentinel",
        "refresh_token_expires_in": 15811200,
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError) as error:
            await GitHubOAuth(settings, client).exchange_code("code", "verifier", "login")

    assert error.value.reason == Reason.PROVIDER_UNAVAILABLE
    assert error.value.status_code == 502
    assert (
        error.value.message
        == "GitHub 로그인 설정이 서비스와 맞지 않습니다. 관리자에게 문의해주세요."
    )
    assert "github_oauth_token_mode_unsupported" in caplog.text
    output = caplog.text + str(error.value.to_envelope())
    assert payload["access_token"] not in output
    assert payload["refresh_token"] not in output
