"""Configuration failures must not silently expose authentication secrets."""

import base64
import importlib

import pytest


def test_public_callback_is_used_for_both_oauth_flows():
    config = importlib.import_module("app.core.config")
    assert hasattr(config, "Settings"), "Session settings must be implemented"
    settings = config.Settings(_env_file=None)
    assert settings.github_redirect_uri == "http://localhost:5173/auth/github/callback"
    assert settings.github_link_redirect_uri == settings.github_redirect_uri
    assert settings.github_login_scope == settings.github_link_scope == "read:user"


def test_startup_rejects_cross_origin_callback_and_insecure_production():
    config = importlib.import_module("app.core.config")
    assert hasattr(config, "Settings"), "Session settings must be implemented"
    values = {
        "_env_file": None,
        "github_client_id": "test-client",
        "github_client_secret": "test-secret",
        "token_encryption_key": base64.b64encode(bytes(range(32))).decode(),
    }
    settings = config.Settings(**values, github_redirect_uri="https://other.example/callback")
    with pytest.raises(ValueError, match="callback"):
        settings.validate_auth()
    settings = config.Settings(**values, app_env="prod")
    with pytest.raises(ValueError, match="HTTPS|Secure"):
        settings.validate_auth()


def test_sensitive_logging_values_are_redacted():
    module = importlib.import_module("app.core.logging")
    assert hasattr(module, "redact_secrets"), "Secret-safe logging must be implemented"
    event = {
        "event": "provider failed",
        "nested": {"access_token": "provider-secret", "devon_session": "sid-secret"},
        "authorization": "Bearer secret",
        "code": "oauth-code",
    }
    output = str(module.redact_secrets(None, "error", event))
    for secret in ("provider-secret", "sid-secret", "Bearer secret", "oauth-code"):
        assert secret not in output
    assert "provider failed" in output


async def test_application_has_real_health_and_error_envelope(app, client):
    health = await client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health.headers["x-request-id"]
    missing = await client.get("/api/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["reason"] == "not_found"
    assert "detail" not in missing.json()


async def test_authenticated_responses_are_not_cached(app, client, db):
    from app.db.models.user import User

    user = User(name="Private profile", status="active")
    db.add(user)
    await db.commit()
    sid = await app.state.sessions.create(user.id)
    response = await client.get("/api/me", headers={"cookie": f"devon_session={sid}"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
