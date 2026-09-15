"""용어사전 §6 enum + error reason 의 코드측 단일 진실. 값은 DB 정의 snake_case 문자열 그대로.

docs/layer-rules.md 3절 · docs/error-reasons.md / task-04
"""

from enum import StrEnum


class JobType(StrEnum):
    """`analysis_jobs.job_type`. docs/pipeline.md 1절."""

    INITIAL_SYNC = "initial_sync"
    ANALYSIS_RUN = "analysis_run"
    INTERVIEW_PREP = "interview_prep"
    DEEP_ANALYSIS = "deep_analysis"


class JobStatus(StrEnum):
    """`analysis_jobs.status` (DB 원본 상태)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"


class RunStatus(StrEnum):
    """FE 계약 상태. DB `partial` 은 `failed` 로 매핑한다."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepKey(StrEnum):
    """분석 run 의 고정 7 step. 순서를 바꾸지 않는다."""

    DOC_EXTRACT = "doc_extract"
    REPO_SELECT = "repo_select"
    REPO_DETAIL = "repo_detail"
    JD_FETCH = "jd_fetch"
    JD_EXTRACT = "jd_extract"
    REPO_ANALYZE = "repo_analyze"
    MATCH_SCORE = "match_score"


class StepStatus(StrEnum):
    """openapi.yaml StepStatus. FE 문서의 completed 와 충돌하면 openapi 를 따른다."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RepoStatus(StrEnum):
    """RepositoryCard.status."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class CandidateSource(StrEnum):
    """RepositoryCard.candidateSource."""

    RULE_FILTER = "rule_filter"
    PORTFOLIO = "portfolio"
    BOTH = "both"


class SelectionReason(StrEnum):
    """`analysis_repo_candidates.selection_reason`."""

    PORTFOLIO_MENTIONED = "portfolio_mentioned"
    BASE_RANK_TOP = "base_rank_top"
    JD_SIGNAL = "jd_signal"
    HIGH_CONTRIBUTION = "high_contribution"
    OTHER = "other"


class FilterStatus(StrEnum):
    """`analysis_repo_candidates.filter_status`."""

    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"


class FilterReason(StrEnum):
    """`analysis_repo_candidates.filter_reason`."""

    PRIVATE = "private"
    FORK = "fork"
    ARCHIVED = "archived"
    NO_LANGUAGE = "no_language"
    TOO_SMALL = "too_small"
    INACCESSIBLE = "inaccessible"


class CandidatePageStatus(StrEnum):
    """`analysis_repo_candidate_pages.status`."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FetchLevel(StrEnum):
    """`repositories.fetch_level`. list=L0-a, detail=L0-b."""

    LIST = "list"
    DETAIL = "detail"


class RequirementType(StrEnum):
    """`jd_requirements.requirement_type`."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    UNKNOWN = "unknown"


class ParseStatus(StrEnum):
    """`job_postings.parse_status`."""

    SUCCESS = "success"
    FAILED = "failed"


class JobErrorCode(StrEnum):
    """`analysis_jobs.error_code`. docs/error-reasons.md Job Error Code."""

    NO_PUBLIC_REPO = "no_public_repo"
    RATE_LIMITED = "rate_limited"
    TOKEN_INVALID = "token_invalid"
    JD_FETCH_FAILED = "jd_fetch_failed"
    JD_EXTRACTION_FAILED = "jd_extraction_failed"
    UNSUPPORTED_SITE = "unsupported_site"
    DOC_EXTRACT_FAILED = "doc_extract_failed"
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE_FAILED = "llm_parse_failed"
    LLM_FAILED = "llm_failed"


class RepoErrorCode(StrEnum):
    """`repo_analyses.error_code` / `repositories.fetch_error_code`."""

    RATE_LIMITED = "rate_limited"
    REPO_UNREACHABLE = "repo_unreachable"
    NO_README = "no_readme"
    INPUT_TOO_LARGE = "input_too_large"
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE_FAILED = "llm_parse_failed"
    LLM_FAILED = "llm_failed"


class PostingParseErrorCode(StrEnum):
    """`job_postings.parse_error_code`."""

    UNSUPPORTED_SITE = "unsupported_site"
    JD_FETCH_FAILED = "jd_fetch_failed"
    JD_EXTRACTION_FAILED = "jd_extraction_failed"
    NOT_A_JOB_POSTING = "not_a_job_posting"


class TokenStatus(StrEnum):
    """`github_accounts.token_status`."""

    VALID = "valid"
    REVOKED = "revoked"


class DocumentExtractStatus(StrEnum):
    """`user_documents.extract_status` / DocumentPreviewResponse.status."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


#: DB status -> FE RunStatus. docs/error-reasons.md Partial Mapping.
JOB_STATUS_TO_RUN_STATUS: dict[JobStatus, RunStatus] = {
    JobStatus.QUEUED: RunStatus.RUNNING,
    JobStatus.RUNNING: RunStatus.RUNNING,
    JobStatus.SUCCEEDED: RunStatus.COMPLETED,
    JobStatus.PARTIAL: RunStatus.FAILED,
    JobStatus.FAILED: RunStatus.FAILED,
    JobStatus.CANCELED: RunStatus.FAILED,
}

#: 진행률/응답에서 고정으로 쓰는 step 순서.
STEP_ORDER: tuple[StepKey, ...] = (
    StepKey.DOC_EXTRACT,
    StepKey.REPO_SELECT,
    StepKey.REPO_DETAIL,
    StepKey.JD_FETCH,
    StepKey.JD_EXTRACT,
    StepKey.REPO_ANALYZE,
    StepKey.MATCH_SCORE,
)
