import base64
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = "postgresql+asyncpg://devon:devon@localhost:5432/devon"


class Settings(DatabaseSettings):
    app_env: Literal["local", "dev", "prod"] = "local"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:5173"
    github_redirect_uri: str = "http://localhost:5173/api/auth/github/callback"
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    jwt_secret_key: SecretStr
    token_encryption_key: SecretStr
    jwt_issuer: str = "devon"
    jwt_audience: str = "devon-api"

    @model_validator(mode="after")
    def validate_auth(self) -> "Settings":
        signing_key = self.jwt_secret_key.get_secret_value().encode()
        try:
            encryption_key = base64.b64decode(
                self.token_encryption_key.get_secret_value(), validate=True
            )
        except ValueError:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be base64") from None
        if len(signing_key) < 32 or len(encryption_key) != 32:
            raise ValueError("JWT key needs at least 32 bytes; AES key needs exactly 32 bytes")
        if signing_key == encryption_key or self.jwt_secret_key == self.token_encryption_key:
            raise ValueError("JWT and encryption keys must be separate")
        has_id = bool(self.github_client_id)
        has_secret = bool(self.github_client_secret.get_secret_value())
        if has_id != has_secret or (self.app_env == "prod" and not has_id):
            raise ValueError("GitHub OAuth credentials are required")
        origin = urlsplit(self.frontend_origin)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("FRONTEND_ORIGIN must be an exact origin without a trailing slash")
        if self.github_redirect_uri != self.frontend_origin + "/api/auth/github/callback":
            raise ValueError(
                "GitHub callback must use the frontend origin and /api/auth/github/callback"
            )
        if self.app_env == "prod" and origin.scheme != "https":
            raise ValueError("Production requires HTTPS")
        return self

    @property
    def cookie_secure(self) -> bool:
        return self.app_env == "prod"
