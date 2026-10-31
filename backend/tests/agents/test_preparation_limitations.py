"""준비 단계의 저장 형식과 저장소별 한계 소비를 DB 없이 검사한다."""

from uuid import UUID

import pytest

from app.db.models import InterviewSession
from app.features.interview.agent_context import _preparation_limitations

REPOSITORY_ID = UUID(int=1)


@pytest.mark.parametrize("state", [None, {}])
def test_missing_preparation_limitations_keeps_existing_context_compatible(state):
    interview = InterviewSession(context_state=state)
    assert _preparation_limitations(interview, REPOSITORY_ID) == ()


@pytest.mark.parametrize("value", [[], {str(REPOSITORY_ID): "목록이 아닌 값"}])
def test_malformed_preparation_limitations_do_not_invent_notes(value):
    interview = InterviewSession(context_state={"preparation_repository_limitations": value})
    assert _preparation_limitations(interview, REPOSITORY_ID) == ()


def test_preparation_limitations_keep_valid_source_text_for_only_the_requested_repository():
    notes = ["  디렉터리 수집 상한에 도달했습니다.  ", "", 7, None, "   ", "README 미확인"]
    interview = InterviewSession(
        context_state={
            "preparation_repository_limitations": {
                str(REPOSITORY_ID): notes,
                str(UUID(int=2)): ["다른 저장소의 한계"],
            }
        }
    )
    assert _preparation_limitations(interview, REPOSITORY_ID) == (
        "  디렉터리 수집 상한에 도달했습니다.  ",
        "README 미확인",
    )
