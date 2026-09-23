"""Stable API reasons; services raise AppError instead of HTTPException."""

from enum import StrEnum
from typing import Any


class Reason(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    GITHUB_TOKEN_INVALID = "github_token_invalid"
    ACCOUNT_SUSPENDED = "account_suspended"
    ACCOUNT_WITHDRAWN = "account_withdrawn"
    INVALID_STATE = "invalid_state"
    INVALID_CODE = "invalid_code"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    GITHUB_ALREADY_LINKED = "github_already_linked"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    INTERNAL_ERROR = "internal_error"


ERRORS: dict[Reason, tuple[int, str]] = {
    Reason.UNAUTHENTICATED: (401, "로그인이 필요합니다."),
    Reason.GITHUB_TOKEN_INVALID: (403, "GitHub 재연동이 필요합니다."),
    Reason.ACCOUNT_SUSPENDED: (403, "정지된 계정입니다."),
    Reason.ACCOUNT_WITHDRAWN: (403, "탈퇴한 계정입니다."),
    Reason.INVALID_STATE: (400, "로그인 요청이 만료되었거나 올바르지 않습니다."),
    Reason.INVALID_CODE: (400, "GitHub 인증 코드가 올바르지 않습니다."),
    Reason.PROVIDER_UNAVAILABLE: (502, "GitHub에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."),
    Reason.GITHUB_ALREADY_LINKED: (409, "현재 사용자와 다른 GitHub 계정은 연동할 수 없습니다."),
    Reason.NOT_FOUND: (404, "요청한 리소스를 찾을 수 없습니다."),
    Reason.INVALID_REQUEST: (400, "요청 형식이 올바르지 않습니다."),
    Reason.INTERNAL_ERROR: (500, "일시적인 오류가 발생했습니다."),
}


class AppError(Exception):
    def __init__(
        self,
        reason: Reason,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
        status_code: int | None = None,
    ) -> None:
        status, default_message = ERRORS[reason]
        self.reason = reason
        self.status_code = status_code if status_code is not None else status
        self.message = message or default_message
        self.details = details or {}
        self.retry_after = retry_after
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "reason": self.reason.value,
            "message": self.message,
            "details": self.details,
        }
        if self.retry_after is not None:
            error["retryAfter"] = self.retry_after
        return {"error": error}
