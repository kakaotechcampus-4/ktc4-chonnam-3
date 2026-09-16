MESSAGES = {
    "unauthenticated": "Authentication is required.",
    "access_token_expired": "The access token expired.",
    "access_token_invalid": "The access token is invalid.",
    "refresh_token_invalid": "The refresh token is invalid.",
    "account_suspended": "This account is suspended.",
    "account_withdrawn": "This account has been withdrawn.",
    "invalid_origin": "The request origin is not allowed.",
    "invalid_state": "The OAuth state is invalid or expired.",
    "invalid_code": "The OAuth authorization code is invalid.",
    "denied": "GitHub authorization was denied.",
    "provider_unavailable": "GitHub is temporarily unavailable.",
    "token_invalid": "The GitHub connection must be authorized again.",
    "service_unavailable": "The service is temporarily unavailable.",
    "internal_error": "An unexpected error occurred.",
}


class AppError(Exception):
    def __init__(self, reason: str, status: int = 401) -> None:
        self.reason = reason
        self.status = status
        super().__init__(reason)

    def envelope(self) -> dict[str, object]:
        return {
            "error": {
                "reason": self.reason,
                "message": MESSAGES.get(self.reason, "The request could not be processed."),
                "details": {},
            }
        }
