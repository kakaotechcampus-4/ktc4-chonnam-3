"""면접 HTTP 진입이 실제 앱에서 인증 경계를 거쳐야 한다."""

import base64
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_interview_lookup_reaches_session_authentication():
    settings = Settings(
        _env_file=None,
        frontend_origin="http://testserver",
        github_redirect_uri="http://testserver/auth/github/callback",
        github_client_id="fixture",
        github_client_secret="fixture",
        token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/interviews/{uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["reason"] == "unauthenticated"


def test_interview_prepare_is_registered_in_the_actual_worker():
    from app.workers.arq_app import WorkerSettings
    from app.workers.tasks.interview_prep import interview_prep

    assert interview_prep in WorkerSettings.functions
    assert WorkerSettings.max_tries == 1
