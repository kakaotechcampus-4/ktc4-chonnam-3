"""AppError + reason 레지스트리. HTTPException 을 직접 raise 하지 않는다.

docs/error-reasons.md / task-05

reason 은 클라이언트가 분기하는 안정적인 snake_case 문자열이다. 값을 추가할 때
spec/shared/contracts/openapi.yaml 과 테스트를 함께 갱신한다.
task-04 에서 app/shared/enums.py 를 만들 때 이 레지스트리와의 일원화를 정리한다.
"""

from enum import StrEnum
from typing import Any


class Reason(StrEnum):
    """API 에러 reason. docs/error-reasons.md 의 HTTP Reason 표와 1:1."""

    # 인증
    UNAUTHENTICATED = "unauthenticated"
    GITHUB_TOKEN_INVALID = "github_token_invalid"
    ACCOUNT_SUSPENDED = "account_suspended"
    ACCOUNT_WITHDRAWN = "account_withdrawn"

    # 문서
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
    DOCUMENT_TOO_LARGE = "document_too_large"
    DOCUMENT_EXTRACT_FAILED = "document_extract_failed"

    # 분석 요청
    POSTING_URL_REQUIRED = "posting_url_required"
    UNSUPPORTED_SITE = "unsupported_site"
    RUN_IN_PROGRESS = "run_in_progress"

    # 분석 조회
    NOT_READY = "not_ready"
    RUN_EXPIRED = "run_expired"

    # 후보 page
    CANDIDATE_PAGE_FAILED = "candidate_page_failed"

    # 면접 생성
    NO_REPOSITORY_SELECTED = "no_repository_selected"
    TOO_MANY_REPOSITORIES = "too_many_repositories"
    INVALID_REPOSITORY = "invalid_repository"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"

    # 면접 준비
    PREP_FAILED = "prep_failed"
    REPO_UNREACHABLE = "repo_unreachable"

    # 면접 준비 재시도
    PREP_IN_PROGRESS = "prep_in_progress"
    SESSION_EXPIRED = "session_expired"

    # 면접 조회
    NOT_FOUND = "not_found"

    # 재시도
    ORIGINAL_NOT_COMPLETED = "original_not_completed"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"

    # 리포트
    REPORT_UNAVAILABLE = "report_unavailable"

    # 이의 제출
    ALREADY_SUBMITTED = "already_submitted"

    # 공통
    INTERNAL_ERROR = "internal_error"
    # ⚠ docs/error-reasons.md 와 openapi.yaml 에 없는 BE 추가 값이다 (PENDING_TEAM).
    #   request body/query 가 스키마를 어겨 RequestValidationError 가 났을 때 쓴다.
    #   엔드포인트별 도메인 reason(posting_url_required 등)으로 잡히지 않는 경우의 fallback 이라
    #   계약에 추가할지 팀 확인이 필요하다.
    INVALID_REQUEST = "invalid_request"


STATUS_BY_REASON: dict[Reason, int] = {
    Reason.UNAUTHENTICATED: 401,
    Reason.GITHUB_TOKEN_INVALID: 403,
    Reason.ACCOUNT_SUSPENDED: 403,
    Reason.ACCOUNT_WITHDRAWN: 403,
    Reason.UNSUPPORTED_DOCUMENT_TYPE: 415,
    Reason.DOCUMENT_TOO_LARGE: 413,
    # 문서 추출 실패는 200 으로 내려보내는 경로도 있다 (extractStatus=failed).
    # 에러 envelope 로 낼 때만 409 다 — hard blocker 가 아니다.
    Reason.DOCUMENT_EXTRACT_FAILED: 409,
    Reason.POSTING_URL_REQUIRED: 400,
    Reason.UNSUPPORTED_SITE: 400,
    Reason.RUN_IN_PROGRESS: 409,
    Reason.NOT_READY: 409,
    Reason.RUN_EXPIRED: 410,
    Reason.CANDIDATE_PAGE_FAILED: 409,
    Reason.NO_REPOSITORY_SELECTED: 400,
    Reason.TOO_MANY_REPOSITORIES: 400,
    Reason.INVALID_REPOSITORY: 400,
    Reason.SESSION_LIMIT_EXCEEDED: 409,
    Reason.PREP_FAILED: 409,
    Reason.REPO_UNREACHABLE: 409,
    Reason.PREP_IN_PROGRESS: 409,
    Reason.SESSION_EXPIRED: 410,
    Reason.NOT_FOUND: 404,
    Reason.ORIGINAL_NOT_COMPLETED: 409,
    Reason.REPOSITORY_UNAVAILABLE: 409,
    Reason.REPORT_UNAVAILABLE: 409,
    Reason.ALREADY_SUBMITTED: 409,
    Reason.INTERNAL_ERROR: 500,
    Reason.INVALID_REQUEST: 400,
}

MESSAGE_BY_REASON: dict[Reason, str] = {
    Reason.UNAUTHENTICATED: "로그인이 필요합니다.",
    Reason.GITHUB_TOKEN_INVALID: "GitHub 연동이 만료되었습니다. 다시 연동해 주세요.",
    Reason.ACCOUNT_SUSPENDED: "정지된 계정입니다.",
    Reason.ACCOUNT_WITHDRAWN: "탈퇴한 계정입니다.",
    Reason.UNSUPPORTED_DOCUMENT_TYPE: "지원하지 않는 파일 형식입니다.",
    Reason.DOCUMENT_TOO_LARGE: "파일 크기가 제한을 넘었습니다.",
    Reason.DOCUMENT_EXTRACT_FAILED: "문서에서 내용을 추출하지 못했습니다.",
    Reason.POSTING_URL_REQUIRED: "공고 URL이 필요합니다.",
    Reason.UNSUPPORTED_SITE: "지원하지 않는 채용 사이트입니다.",
    Reason.RUN_IN_PROGRESS: "이미 진행 중인 분석이 있습니다.",
    Reason.NOT_READY: "아직 결과가 준비되지 않았습니다.",
    Reason.RUN_EXPIRED: "만료된 분석입니다. 다시 시작해 주세요.",
    Reason.CANDIDATE_PAGE_FAILED: "추가 레포지토리 분석에 실패했습니다.",
    Reason.NO_REPOSITORY_SELECTED: "레포지토리를 1개 이상 선택해 주세요.",
    Reason.TOO_MANY_REPOSITORIES: "레포지토리는 최대 5개까지 선택할 수 있습니다.",
    Reason.INVALID_REPOSITORY: "선택할 수 없는 레포지토리입니다.",
    Reason.SESSION_LIMIT_EXCEEDED: "이미 진행 중인 면접이 있습니다.",
    Reason.PREP_FAILED: "면접 준비에 실패했습니다.",
    Reason.REPO_UNREACHABLE: "레포지토리에 접근하지 못했습니다.",
    Reason.PREP_IN_PROGRESS: "이미 다시 준비하고 있습니다.",
    Reason.SESSION_EXPIRED: "면접 세션이 만료되었습니다. 레포지토리를 다시 선택해 주세요.",
    Reason.NOT_FOUND: "요청한 리소스를 찾을 수 없습니다.",
    Reason.ORIGINAL_NOT_COMPLETED: "완료되거나 중단된 면접만 다시 시작할 수 있습니다.",
    Reason.REPOSITORY_UNAVAILABLE: "원본 면접의 레포지토리를 사용할 수 없습니다.",
    Reason.REPORT_UNAVAILABLE: "리포트를 생성할 수 없는 면접입니다.",
    Reason.ALREADY_SUBMITTED: "이미 제출한 이의입니다.",
    Reason.INTERNAL_ERROR: "일시적인 오류가 발생했습니다.",
    Reason.INVALID_REQUEST: "요청 형식이 올바르지 않습니다.",
}

# ── 내부 job error_code ─────────────────────────────────────────
# ⚠ API reason 과 다른 축이다. 응답 envelope 의 reason 으로 내보내지 않는다.
#   DB 컬럼(analysis_jobs.error_code 등)에 기록해 실패 원인을 남기는 용도다.
#   token_invalid 처럼 글자가 같은 값이 있어도 의미와 쓰임이 다르다.
ANALYSIS_JOB_ERROR_CODES = frozenset(
    {
        "no_public_repo",
        "rate_limited",
        "token_invalid",
        "jd_fetch_failed",
        "jd_extraction_failed",
        "unsupported_site",
        "doc_extract_failed",
        "llm_timeout",
        "llm_parse_failed",
        "llm_failed",
    }
)
REPO_ANALYSIS_ERROR_CODES = frozenset(
    {
        "rate_limited",
        "repo_unreachable",
        "no_readme",
        "input_too_large",
        "llm_timeout",
        "llm_parse_failed",
        "llm_failed",
    }
)
JOB_POSTING_PARSE_ERROR_CODES = frozenset(
    {
        "unsupported_site",
        "jd_fetch_failed",
        "jd_extraction_failed",
        "not_a_job_posting",
    }
)

# DB analysis_jobs.status -> FE RunStatus. partial 은 failed 로 접는다.
# 단 /analysis-runs/{runId}/result 는 partial 이어도 조회 가능하다.
RUN_STATUS_BY_JOB_STATUS: dict[str, str] = {
    "queued": "running",
    "running": "running",
    "succeeded": "completed",
    "partial": "failed",
    "failed": "failed",
    "canceled": "failed",
}


def to_run_status(job_status: str) -> str:
    """DB job status 를 FE RunStatus 3종으로 접는다.

    입력: analysis_jobs.status. 출력: running | completed | failed.
    """
    return RUN_STATUS_BY_JOB_STATUS[job_status]


class AppError(Exception):
    """API 에러. router·service 는 HTTPException 대신 이것만 raise 한다.

    FastAPI 기본 detail 응답이 새면 계약 위반이므로 전역 핸들러가 envelope 로 감싼다.
    """

    def __init__(
        self,
        reason: Reason,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
        status_code: int | None = None,
    ) -> None:
        """입력: reason(필수), 나머지는 선택. 출력: 없음.

        message 를 비우면 MESSAGE_BY_REASON 의 기본 문구를 쓴다.
        status_code 는 document_extract_failed 처럼 상황에 따라 다른 경우에만 넘긴다.
        """
        self.reason = reason
        self.message = message or MESSAGE_BY_REASON[reason]
        self.details = details or {}
        self.retry_after = retry_after
        self.status_code = status_code or STATUS_BY_REASON[reason]
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        """openapi ApiError 모양으로 만든다. 출력: {"error": {...}}."""
        error: dict[str, Any] = {
            "reason": self.reason.value,
            "message": self.message,
            "details": self.details,
        }
        if self.retry_after is not None:
            error["retryAfter"] = self.retry_after
        return {"error": error}
