"""면접 생성 요청/응답 스키마. openapi CreateInterviewRequest / CreateInterviewResponse.

task-13
"""

import uuid

import pytest
from pydantic import ValidationError

from app.features.interview.schemas import CreateInterviewRequest, CreateInterviewResponse


@pytest.mark.parametrize("count", [0, 6])
def test_request_leaves_count_check_to_service(count: int) -> None:
    """개수 제한을 스키마가 막으면 계약 reason 대신 invalid_request 가 나간다."""
    ids = [str(uuid.uuid4()) for _ in range(count)]
    body = CreateInterviewRequest.model_validate({"runId": str(uuid.uuid4()), "repositoryIds": ids})
    assert len(body.repository_ids) == count


def test_request_rejects_non_uuid() -> None:
    with pytest.raises(ValidationError):
        CreateInterviewRequest.model_validate({"runId": "run-1", "repositoryIds": []})


def test_response_is_camel_case() -> None:
    interview_id = uuid.uuid4()
    dumped = CreateInterviewResponse(session_id="s", interview_id=interview_id).model_dump(
        mode="json"
    )
    assert dumped == {"sessionId": "s", "interviewId": str(interview_id)}
