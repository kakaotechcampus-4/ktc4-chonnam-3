"""Task 11 요청·응답. 카드 정의는 선행 Task 10 스키마를 재사용한다."""

import uuid

from pydantic import Field

from app.features.analysis.schemas import RepositoryCard
from app.shared.enums import JdCategory, RunStatus, StepKey, StepStatus
from app.shared.schema import CamelModel, CamelResponse


class CreateAnalysisRunRequest(CamelModel):
    # 누락·빈 URL은 공통 invalid_request 대신 posting_url_required로 처리한다.
    posting_url: str | None = None
    document_id: uuid.UUID | None = None


class CreateAnalysisRunResponse(CamelResponse):
    run_id: uuid.UUID


class AnalysisStep(CamelResponse):
    key: StepKey
    status: StepStatus


class AnalysisRunResponse(CamelResponse):
    run_id: uuid.UUID
    status: RunStatus
    steps: list[AnalysisStep]
    progress: int = Field(ge=0, le=100)
    failure_reason: str | None
    estimated_seconds: int | None


class JdRequirementResponse(CamelResponse):
    id: uuid.UUID
    category: JdCategory
    text: str
    display_order: int


class FailedRepository(CamelResponse):
    repository_id: uuid.UUID
    error_code: str


class AnalysisRunResultResponse(CamelResponse):
    run_id: uuid.UUID
    position: str
    company_name: str | None
    jd_requirements: list[JdRequirementResponse]
    mentioned_repo_count: int = Field(ge=0)
    matched_repo_count: int = Field(ge=0)
    repositories: list[RepositoryCard]
    analyzed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    failed_repositories: list[FailedRepository]


class CandidatesResponse(CamelResponse):
    repositories: list[RepositoryCard]


class AnalyzingResponse(CamelResponse):
    status: str = "analyzing"
    retry_after: int = 3
