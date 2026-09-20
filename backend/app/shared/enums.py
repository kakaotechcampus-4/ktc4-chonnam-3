"""용어사전 §6 enum + error reason 의 코드측 단일 진실. 값은 DB 정의 snake_case 문자열 그대로.

docs/layer-rules.md 3절 · docs/error-reasons.md / task-04

클래스 이름은 spec/shared/contracts/openapi.yaml 의 schema 이름과 일치시킨다.
tests/contract/test_openapi_enums.py 가 이름으로 짝지어 값 집합을 대조하므로
한쪽만 바꾸면 테스트가 깨진다.
"""

from enum import StrEnum


# task-05 에서 core/errors.py 에 뒀던 Reason 을 여기로 옮겼다.
# reason 값의 단일 진실은 이 모듈이고, HTTP 상태·메시지 매핑과 AppError 는
# core/errors.py 가 계속 소유한다 (core -> shared 한 방향 import).
class Reason(StrEnum):
    """API 에러 reason. docs/error-reasons.md 의 HTTP Reason 표와 1:1."""

    # 인증
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_INVALID = "token_invalid"
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


class AnalysisStatus(StrEnum):
    """/me/home 의 사용자 분석 상태."""

    SYNCING = "syncing"
    NO_REPOSITORY = "no_repository"
    NO_INTERVIEW = "no_interview"
    COMPLETED = "completed"


class RunStatus(StrEnum):
    """FE 가 보는 분석 run 상태 3종.

    DB analysis_jobs.status 는 6종이다. partial/failed/canceled 가 여기서 failed 로 접힌다.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InterviewStatus(StrEnum):
    """면접 상태. DB interview_sessions.status 와 값이 같다."""

    PREPARING = "preparing"
    PREPARING_FAILED = "preparing_failed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class StepKey(StrEnum):
    """분석 7단계. 응답에는 실행되지 않은 step 도 항상 7개가 다 담긴다."""

    DOC_EXTRACT = "doc_extract"
    REPO_SELECT = "repo_select"
    REPO_DETAIL = "repo_detail"
    JD_FETCH = "jd_fetch"
    JD_EXTRACT = "jd_extract"
    REPO_ANALYZE = "repo_analyze"
    MATCH_SCORE = "match_score"


class PrepareStepKey(StrEnum):
    """면접 준비 4단계."""

    ANALYZE_REPO = "analyze_repo"
    BUILD_PERSONA = "build_persona"
    COMPOSE_QUESTION = "compose_question"
    SET_CRITERIA = "set_criteria"


class StepStatus(StrEnum):
    """단계 상태.

    skipped 는 입력이 없어 실행하지 않은 정상 경로다. failed 와 구분하며 progress 에서 뺀다.
    StepKey 에만 적용한다.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnswerMode(StrEnum):
    """Sprint 1 은 텍스트 고정. 음성은 Sprint 2."""

    TEXT = "text"


class DocumentExtractStatus(StrEnum):
    """문서 추출 결과. partial 은 일부만 추출했거나 길이 초과로 축약한 경우다."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class RepoStatus(StrEnum):
    """레포 카드에 표시하는 분석 상태."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class CandidateSource(StrEnum):
    """후보가 어디서 왔는지. portfolio 는 포트폴리오에서 언급된 repo 다."""

    RULE_FILTER = "rule_filter"
    PORTFOLIO = "portfolio"
    BOTH = "both"


class JdCategory(StrEnum):
    """공고 요구사항 분류. unknown 버킷은 두지 않는다 (2026-09-21 결정)."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    RESPONSIBILITY = "responsibility"


class Persona(StrEnum):
    """면접관 3인."""

    TECH_LEAD = "tech_lead"
    HR_MANAGER = "hr_manager"
    DOMAIN_LEAD = "domain_lead"


class ScoreKey(StrEnum):
    """리포트 점수 항목 6종. totalScore 는 이 6개의 단순 평균이다."""

    PROJECT_UNDERSTANDING = "project_understanding"
    TECHNICAL_REASONING = "technical_reasoning"
    PROBLEM_SOLVING = "problem_solving"
    COMMUNICATION = "communication"
    CONTRIBUTION_CLARITY = "contribution_clarity"
    COMPANY_JOB_FIT = "company_job_fit"


class ReasonType(StrEnum):
    """리포트 이의 제기 사유. Sprint 2 에서 사용한다."""

    FACTUAL_ERROR = "factual_error"
    INSUFFICIENT_BASIS = "insufficient_basis"
    OVERLY_HARSH = "overly_harsh"
    UNCLEAR_INTENT = "unclear_intent"
    OTHER = "other"


# DB analysis_jobs.status -> FE RunStatus.
# task-05 에서 core/errors.py 에 뒀으나 에러가 아니라 enum 매핑이라 여기로 옮겼다.
RUN_STATUS_BY_JOB_STATUS: dict[str, RunStatus] = {
    "queued": RunStatus.RUNNING,
    "running": RunStatus.RUNNING,
    "succeeded": RunStatus.COMPLETED,
    # partial 이어도 /analysis-runs/{runId}/result 는 조회 가능하다.
    "partial": RunStatus.FAILED,
    "failed": RunStatus.FAILED,
    "canceled": RunStatus.FAILED,
}


def to_run_status(job_status: str) -> RunStatus:
    """DB job status 를 FE RunStatus 3종으로 접는다.

    입력: analysis_jobs.status. 출력: RunStatus.
    """
    return RUN_STATUS_BY_JOB_STATUS[job_status]
