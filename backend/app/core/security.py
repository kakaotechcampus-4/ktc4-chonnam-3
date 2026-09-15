import time
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt

from app.core.config import Settings
from app.core.errors import AppError

ACCESS_TTL = 900
REFRESH_TTL = 1209600
TokenType = Literal["access", "refresh"]


class Tokens:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def encode(
        self,
        user_id: str,
        kind: TokenType,
        *,
        sid: str | None = None,
        generation: str | None = None,
        jti: str | None = None,
    ) -> str:
        now = int(time.time())
        extra = {"sid": sid, "generation": generation} if kind == "refresh" else {}
        return jwt.encode(
            {
                "sub": user_id,
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
                "type": kind,
                "iat": now,
                "exp": now + (ACCESS_TTL if kind == "access" else REFRESH_TTL),
                "jti": jti or str(uuid4()),
                **extra,
            },
            self.settings.jwt_secret_key.get_secret_value(),
            algorithm="HS256",
        )

    def access(self, user_id: str) -> str:
        return self.encode(user_id, "access")

    def decode(self, token: str, kind: TokenType) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self.settings.jwt_secret_key.get_secret_value(),
                algorithms=["HS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={
                    "require": ["sub", "iss", "aud", "type", "iat", "exp", "jti"],
                    "verify_exp": False,
                    "strict_aud": True,
                },
            )
            if claims["type"] != kind:
                raise ValueError("Wrong token type")
            if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
                raise ValueError("Invalid timestamp type")
            UUID(claims["sub"])
            UUID(claims["jti"])
            if kind == "refresh":
                UUID(claims["sid"])
                UUID(claims["generation"])
            if claims["exp"] <= time.time():
                raise jwt.ExpiredSignatureError()
            return claims
        except jwt.ExpiredSignatureError:
            raise AppError(
                "access_token_expired" if kind == "access" else "refresh_token_invalid"
            ) from None
        except (jwt.InvalidTokenError, ValueError, KeyError, TypeError, AttributeError):
            raise AppError(f"{kind}_token_invalid") from None
