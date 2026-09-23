"""Configuration shared by HTTP, workers and migrations."""

import base64
import binascii
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["local", "dev", "prod"] = "local"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"
    log_level: LogLevel = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://devon:devon@localhost:5432/devon", repr=False
    )
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    session_cookie_name: str = "devon_session"
    session_ttl_seconds: int = Field(default=1209600, gt=0)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax"] = "lax"
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_login_scope: str = "read:user"
    github_link_scope: str = "read:user"
    github_redirect_uri: str = "http://localhost:5173/auth/github/callback"
    token_encryption_key: SecretStr = SecretStr("")

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def github_link_redirect_uri(self) -> str:
        return self.github_redirect_uri

    def validate_auth(self) -> None:
        """Fail startup without exposing secrets if OAuth settings are inconsistent."""
        origin = urlsplit(self.frontend_origin)
        callback = urlsplit(self.github_redirect_uri)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.netloc
            or origin.username is not None
            or origin.password is not None
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or (callback.scheme, callback.netloc) != (origin.scheme, origin.netloc)
            or callback.path != "/auth/github/callback"
            or callback.query
            or callback.fragment
        ):
            raise ValueError("OAuth callback must be FRONTEND_ORIGIN/auth/github/callback")
        if self.is_prod and (origin.scheme != "https" or not self.cookie_secure):
            raise ValueError("Production requires HTTPS and Secure session cookies")
        if self.api_prefix != "/api" or self.session_cookie_name != "devon_session":
            raise ValueError("Sprint 1 requires /api and the devon_session cookie")
        if self.github_login_scope != "read:user" or self.github_link_scope != "read:user":
            raise ValueError("Sprint 1 GitHub scope must be read:user")
        if not self.github_client_id or not self.github_client_secret.get_secret_value():
            raise ValueError("GitHub OAuth client credentials must be configured")
        try:
            key = base64.b64decode(self.token_encryption_key.get_secret_value(), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key") from None
        if len(key) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key")


@lru_cache
def get_settings() -> Settings:
    return Settings()
