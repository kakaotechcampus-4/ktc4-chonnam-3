"""기존 분석 상태 조회 계약."""

import uuid

from pydantic import Field

from app.shared.enums import RunStatus, StepKey, StepStatus
from app.shared.schema import CamelResponse


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
