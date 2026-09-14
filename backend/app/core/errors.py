"""AppError + reason 레지스트리. HTTPException 을 직접 raise 하지 않는다.

docs/error-reasons.md / task-05
"""

from enum import StrEnum
from typing import Any


class ErrorReason(StrEnum):
    """API 표면의 error.reason. 내부 job error_code 와 분리한다."""

    # 인증
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_INVALID = "token_invalid"
    ACCOUNT_SUSPENDED = "account_suspended"
    ACCOUNT_WITHDRAWN = "account_withdrawn"
    # 문서
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
    DOCUMENT_TOO_LARGE = "document_too_large"
    DOCUMENT_EXTRACT_FAILED = "document_extract_failed"
    DOCUMENT_NOT_FOUND = "document_not_found"
    # 분석 요청
    POSTING_URL_REQUIRED = "posting_url_required"
    UNSUPPORTED_SITE = "unsupported_site"
    RUN_IN_PROGRESS = "run_in_progress"
    # 분석 조회
    NOT_READY = "not_ready"
    RUN_EXPIRED = "run_expired"
    # 후보 page
    CANDIDATE_PAGE_FAILED = "candidate_page_failed"
    # 면접 생성 / 준비 / 조회
    NO_REPOSITORY_SELECTED = "no_repository_selected"
    TOO_MANY_REPOSITORIES = "too_many_repositories"
    INVALID_REPOSITORY = "invalid_repository"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    PREP_FAILED = "prep_failed"
    REPO_UNREACHABLE = "repo_unreachable"
    NOT_FOUND = "not_found"
    # 재시도 / 리포트 / 이의
    ORIGINAL_NOT_COMPLETED = "original_not_completed"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    REPORT_UNAVAILABLE = "report_unavailable"
    ALREADY_SUBMITTED = "already_submitted"
    # 공통
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"


#: reason -> HTTP status. docs/error-reasons.md HTTP Reason 표와 1:1.
REASON_STATUS: dict[ErrorReason, int] = {
    ErrorReason.UNAUTHENTICATED: 401,
    ErrorReason.TOKEN_INVALID: 403,
    ErrorReason.ACCOUNT_SUSPENDED: 403,
    ErrorReason.ACCOUNT_WITHDRAWN: 403,
    ErrorReason.UNSUPPORTED_DOCUMENT_TYPE: 415,
    ErrorReason.DOCUMENT_TOO_LARGE: 413,
    ErrorReason.DOCUMENT_EXTRACT_FAILED: 409,
    ErrorReason.DOCUMENT_NOT_FOUND: 400,
    ErrorReason.POSTING_URL_REQUIRED: 400,
    ErrorReason.UNSUPPORTED_SITE: 400,
    ErrorReason.RUN_IN_PROGRESS: 409,
    ErrorReason.NOT_READY: 409,
    ErrorReason.RUN_EXPIRED: 410,
    ErrorReason.CANDIDATE_PAGE_FAILED: 409,
    ErrorReason.NO_REPOSITORY_SELECTED: 400,
    ErrorReason.TOO_MANY_REPOSITORIES: 400,
    ErrorReason.INVALID_REPOSITORY: 400,
    ErrorReason.SESSION_LIMIT_EXCEEDED: 409,
    ErrorReason.PREP_FAILED: 409,
    ErrorReason.REPO_UNREACHABLE: 409,
    ErrorReason.NOT_FOUND: 404,
    ErrorReason.ORIGINAL_NOT_COMPLETED: 409,
    ErrorReason.REPOSITORY_UNAVAILABLE: 409,
    ErrorReason.REPORT_UNAVAILABLE: 409,
    ErrorReason.ALREADY_SUBMITTED: 409,
    ErrorReason.VALIDATION_FAILED: 422,
    ErrorReason.INTERNAL_ERROR: 500,
}

#: 기본 사용자 메시지. 화면 문구는 FE 가 reason 으로 분기하므로 최소한만 둔다.
REASON_MESSAGE: dict[ErrorReason, str] = {
    ErrorReason.UNAUTHENTICATED: "로그인이 필요합니다.",
    ErrorReason.TOKEN_INVALID: "GitHub 재연동이 필요합니다.",
    ErrorReason.ACCOUNT_SUSPENDED: "이용이 정지된 계정입니다.",
    ErrorReason.ACCOUNT_WITHDRAWN: "탈퇴한 계정입니다.",
    ErrorReason.UNSUPPORTED_DOCUMENT_TYPE: "지원하지 않는 파일 형식입니다.",
    ErrorReason.DOCUMENT_TOO_LARGE: "파일 크기가 너무 큽니다.",
    ErrorReason.DOCUMENT_EXTRACT_FAILED: "문서에서 텍스트를 추출하지 못했습니다.",
    ErrorReason.DOCUMENT_NOT_FOUND: "선택할 수 없는 문서입니다.",
    ErrorReason.POSTING_URL_REQUIRED: "공고 URL이 필요합니다.",
    ErrorReason.UNSUPPORTED_SITE: "지원하지 않는 공고 사이트입니다.",
    ErrorReason.RUN_IN_PROGRESS: "이미 진행 중인 분석이 있습니다.",
    ErrorReason.NOT_READY: "아직 결과가 준비되지 않았습니다.",
    ErrorReason.RUN_EXPIRED: "분석 결과가 만료되었습니다.",
    ErrorReason.CANDIDATE_PAGE_FAILED: "후보 페이지 분석에 실패했습니다.",
    ErrorReason.NO_REPOSITORY_SELECTED: "레포지토리를 1개 이상 선택해야 합니다.",
    ErrorReason.TOO_MANY_REPOSITORIES: "선택할 수 있는 레포지토리 수를 초과했습니다.",
    ErrorReason.INVALID_REPOSITORY: "선택할 수 없는 레포지토리입니다.",
    ErrorReason.SESSION_LIMIT_EXCEEDED: "진행 중인 면접이 있습니다.",
    ErrorReason.PREP_FAILED: "면접 준비에 실패했습니다.",
    ErrorReason.REPO_UNREACHABLE: "레포지토리에 접근할 수 없습니다.",
    ErrorReason.NOT_FOUND: "대상을 찾을 수 없습니다.",
    ErrorReason.ORIGINAL_NOT_COMPLETED: "완료된 면접만 재시도할 수 있습니다.",
    ErrorReason.REPOSITORY_UNAVAILABLE: "레포지토리를 사용할 수 없습니다.",
    ErrorReason.REPORT_UNAVAILABLE: "리포트를 생성할 수 없습니다.",
    ErrorReason.ALREADY_SUBMITTED: "이미 제출했습니다.",
    ErrorReason.VALIDATION_FAILED: "요청 값이 올바르지 않습니다.",
    ErrorReason.INTERNAL_ERROR: "일시적인 오류가 발생했습니다.",
}


class AppError(Exception):
    """모든 4xx/5xx 의 단일 출구. FastAPI HTTPException 을 대신한다."""

    def __init__(
        self,
        reason: ErrorReason,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.reason = reason
        self.message = message or REASON_MESSAGE[reason]
        self.details: dict[str, Any] = details or {}
        self.status_code = status_code or REASON_STATUS[reason]
        super().__init__(f"{reason}: {self.message}")

    def to_envelope(self) -> dict[str, Any]:
        """`{error: {reason, message, details}}` 봉투."""
        return {
            "error": {
                "reason": str(self.reason),
                "message": self.message,
                "details": self.details,
            }
        }
