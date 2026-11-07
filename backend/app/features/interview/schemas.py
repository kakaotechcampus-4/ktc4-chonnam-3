"""면접 요청/응답 스키마. 필드는 공통 OpenAPI 와 맞춘다.
재도전(/{id}/retry)은 CreateInterviewResponse 를 재사용하고, 준비 재시도는 본문이 없다.
DB·API 상태는 preparing / preparing_failed / in_progress / completed / abandoned다.

docs/pipeline.md 4.5절 / task-04
"""

import uuid
from datetime import datetime

from app.shared.enums import AnswerMode, InterviewStatus, Persona, PrepareStepKey
from app.shared.schema import CamelModel, CamelResponse


class CreateInterviewRequest(CamelModel):
    """openapi CreateInterviewRequest.

    repositoryIds 의 1~5개 제한은 여기서 걸지 않는다. 스키마에서 막으면 invalid_request 가
    되어 계약 reason(no_repository_selected / too_many_repositories)이 나가지 않으므로
    service 가 검사한다.
    형식이 UUID 가 아닌 id 는 우리 API 가 준 값이 아니므로 invalid_request 로 둔다.
    """

    run_id: uuid.UUID
    repository_ids: list[uuid.UUID]


class CreateInterviewResponse(CamelResponse):
    """openapi CreateInterviewResponse. 201."""

    session_id: str
    interview_id: uuid.UUID


class InterviewTurn(CamelResponse):
    """openapi InterviewTurn."""

    turn: int
    persona: Persona
    question: str
    answer: str | None


class InterviewLastError(CamelResponse):
    """openapi InterviewLastError. DB last_error JSONB 가 이 모양(camelCase)으로 저장된다."""

    reason: str
    code: str
    step: PrepareStepKey | None
    recoverable: bool
    occurred_at: datetime


class InterviewDetailResponse(CamelResponse):
    """openapi InterviewDetailResponse. 200.

    prepareSteps 는 BE 명세엔 있으나 openapi 에 없어 넣지 않는다 (FE 는 WS 로 받는다).
    """

    id: uuid.UUID
    session_id: str
    run_id: uuid.UUID
    status: InterviewStatus
    answer_mode: AnswerMode
    position: str
    company_name: str | None
    repository_names: list[str]
    current_turn: int
    total_turns: int
    remaining_seconds: int
    turns: list[InterviewTurn]
    last_error: InterviewLastError | None
