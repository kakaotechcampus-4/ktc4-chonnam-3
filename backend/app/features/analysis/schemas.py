"""분석 요청/응답 스키마.

원본은 spec/shared/contracts/openapi.yaml 이다. FE 문서(frontend/docs/api-spec.md)와
충돌하는 항목은 openapi 를 따르고, openapi 에 없고 FE 화면에만 필요한 필드는 추가로 싣는다.

- 분석 실패는 HTTP 200 + failureReason (4xx 를 내면 FE 의 queryCache.onError 가 걸린다).
- failureReason 은 analysis_jobs.error_code 를 그대로 쓴다 (경계 매핑 레이어를 두지 않는다).
- DB status='partial' 은 FE RunStatus 로 'failed' 이며 result 조회는 계속 가능하다.

확정본 §3 / task-04 · task-11
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.shared.enums import (
    CandidateSource,
    RepoStatus,
    RequirementType,
    RunStatus,
    StepKey,
    StepStatus,
)
from app.shared.schema import CamelModel


class CreateAnalysisRunRequest(CamelModel):
    """POST /analysis-runs."""

    posting_url: str = Field(min_length=1)
    document_id: uuid.UUID | None = None


class CreateAnalysisRunResponse(CamelModel):
    """202. reused=true 면 진행 중인 동일 fingerprint run 을 그대로 돌려준 것이다."""

    run_id: uuid.UUID
    status: RunStatus
    reused: bool = False


class StepState(CamelModel):
    """진행률 폴링의 step 1개."""

    key: StepKey
    status: StepStatus


class AnalysisRunResponse(CamelModel):
    """GET /analysis-runs/{runId}. 실패도 200 이다."""

    run_id: uuid.UUID
    status: RunStatus
    progress: int = Field(ge=0, le=100)
    steps: list[StepState]
    failure_reason: str | None = None
    estimated_seconds: int | None = None


class LanguageRatio(CamelModel):
    """언어 비중(%). GitHub languages byte 수를 BE 가 백분율로 바꾼다."""

    name: str
    ratio: float


class RepositoryCard(CamelModel):
    """레포 목록 카드. AI 미완료 구간은 null/false 로 내려간다."""

    repository_id: uuid.UUID
    full_name: str
    name: str
    description: str | None = None
    languages: list[LanguageRatio] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    stars: int = 0
    forks: int = 0
    commit_count: int | None = None
    user_commit_count: int | None = None
    pushed_at: datetime | None = None
    status: RepoStatus
    error_code: str | None = None
    recommended: bool = False
    candidate_source: CandidateSource = CandidateSource.RULE_FILTER
    recommend_reason: str | None = None
    match_score: float | None = None
    matched_requirement_ids: list[uuid.UUID] = Field(default_factory=list)


class JdRequirementItem(CamelModel):
    """공고 요구사항 1줄 (FE 우측 패널)."""

    id: uuid.UUID
    type: RequirementType
    text: str


class FailedRepository(CamelModel):
    """부분 실패 목록. openapi AnalysisRunResultResponse.failedRepositories."""

    repository_id: uuid.UUID
    error_code: str


class AnalysisRunResultResponse(CamelModel):
    """GET /analysis-runs/{runId}/result. partial run 도 조회 가능하다."""

    run_id: uuid.UUID
    status: RunStatus
    analyzed_count: int
    failed_count: int
    failed_repositories: list[FailedRepository] = Field(default_factory=list)
    repositories: list[RepositoryCard] = Field(default_factory=list)
    # openapi 에는 없지만 5a-v2 화면이 요구하는 부가 필드 (frontend/docs/api-spec.md 15).
    position: str | None = None
    company_name: str | None = None
    jd_requirements: list[JdRequirementItem] = Field(default_factory=list)
    mentioned_repo_count: int = 0
    matched_repo_count: int = 0


class CandidatePageResponse(CamelModel):
    """GET /analysis-runs/{runId}/candidates?page=N — 분석 완료 page."""

    run_id: uuid.UUID
    page: int
    repositories: list[RepositoryCard] = Field(default_factory=list)


class AnalyzingResponse(CamelModel):
    """202. retryAfter 간격으로 재조회한다."""

    status: str = "analyzing"
    retry_after: int
