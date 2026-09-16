import base64
import logging
import secrets
from uuid import uuid4

import jwt
import pytest
from cryptography.exceptions import InvalidTag

from app.core import config, crypto, security
from app.core.errors import AppError
from app.core.logging import AuthRedactionFilter


def settings():
    assert hasattr(config, "Settings"), "Authentication settings must exist"
    return config.Settings(
        _env_file=None,
        github_client_id="test-client",
        github_client_secret="test-client-secret",
        jwt_secret_key=secrets.token_urlsafe(48),
        token_encryption_key=base64.b64encode(secrets.token_bytes(32)).decode(),
    )


def test_encryption_authenticates_and_randomizes_ciphertext():
    cfg = settings()
    cipher = crypto.TokenCipher(cfg)
    first = cipher.encrypt("github-secret")
    assert first != cipher.encrypt("github-secret")
    assert b"github-secret" not in first
    assert cipher.decrypt(first) == "github-secret"
    with pytest.raises(InvalidTag):
        cipher.decrypt(first[:-1] + bytes([first[-1] ^ 1]))


def test_jwt_type_signature_and_expiry_are_enforced():
    cfg = settings()
    tokens = security.Tokens(cfg)
    user_id = str(uuid4())
    token = tokens.access(user_id)
    assert tokens.decode(token, "access")["sub"] == user_id
    with pytest.raises(AppError, match="refresh_token_invalid"):
        tokens.decode(token, "refresh")
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["exp"] = claims["iat"] - 1
    expired = jwt.encode(claims, cfg.jwt_secret_key.get_secret_value(), algorithm="HS256")
    with pytest.raises(AppError, match="access_token_expired"):
        tokens.decode(expired, "access")
    with pytest.raises(AppError, match="access_token_invalid"):
        tokens.decode(token + "tampered", "access")


def test_settings_reject_missing_or_weak_keys():
    assert hasattr(config, "Settings"), "Authentication settings must exist"
    with pytest.raises(ValueError):
        config.Settings(_env_file=None, jwt_secret_key="weak")


@pytest.mark.parametrize(
    "changed", [{"type": "refresh"}, {"aud": "another-app"}, {"jti": "not-a-uuid"}, {"iat": "123"}]
)
def test_expired_but_invalid_access_is_not_refreshable(changed):
    cfg = settings()
    tokens = security.Tokens(cfg)
    claims = jwt.decode(tokens.access(str(uuid4())), options={"verify_signature": False})
    claims.update(changed)
    claims["exp"] = 1
    invalid = jwt.encode(claims, cfg.jwt_secret_key.get_secret_value(), algorithm="HS256")
    with pytest.raises(AppError, match="access_token_invalid"):
        tokens.decode(invalid, "access")


def test_local_missing_oauth_credentials_is_allowed_but_partial_or_prod_is_not():
    values = settings().model_dump()
    values.update(github_client_id="", github_client_secret="")
    config.Settings(_env_file=None, **values)
    with pytest.raises(ValueError):
        config.Settings(_env_file=None, **{**values, "github_client_id": "partial"})
    with pytest.raises(ValueError):
        config.Settings(
            _env_file=None,
            **{
                **values,
                "app_env": "prod",
                "frontend_origin": "https://devon.test",
                "github_redirect_uri": "https://devon.test/api/auth/github/callback",
            },
        )


def test_auth_logs_redact_query_cookies_and_bearer():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "GET /api/auth/github/callback?code=secret-code&state=secret-state HTTP/1.1" '
        "302 Cookie: accessToken=secret-jwt; refreshToken=secret-refresh "
        "Authorization: Bearer secret-bearer",
        ("127.0.0.1",),
        None,
    )
    AuthRedactionFilter().filter(record)
    assert "secret" not in record.getMessage()
    assert "GET /api/auth/github/callback" in record.getMessage()


def test_redaction_keeps_uvicorn_access_formatter_arguments():
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/api/auth/github/callback?code=secret&state=secret", "1.1", 302),
        None,
    )
    AuthRedactionFilter().filter(record)
    rendered = AccessFormatter("%(client_addr)s %(request_line)s %(status_code)s").format(record)
    assert "secret" not in rendered and "302" in rendered


@pytest.mark.parametrize(
    "target",
    [
        "/api/auth/github/callback?%63ode=secret-code&%73tate=secret-state",
        "/api/auth/github/%63allback?%63ode=secret-code&%73tate=secret-state",
    ],
)
def test_percent_encoded_callback_parameters_are_redacted(target):
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", target, "1.1", 302),
        None,
    )
    AuthRedactionFilter().filter(record)
    assert "secret" not in AccessFormatter("%(request_line)s").format(record)
