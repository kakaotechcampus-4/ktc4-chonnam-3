"""면접 요청/응답 스키마. 필드는 공통 OpenAPI 와 맞춘다.
현재 POST /interviews 의 요청·응답만 있다. GET /interviews/{id} 등은 구현 예정.
DB·API 상태는 preparing / preparing_failed / in_progress / completed / abandoned다.

docs/pipeline.md 4.5절 / task-04
"""

import uuid

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
