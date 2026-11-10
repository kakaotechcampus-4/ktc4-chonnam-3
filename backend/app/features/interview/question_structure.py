"""질문 관계를 같은 면접의 확정된 부모 턴에 결합한다."""

from uuid import UUID

from devon_ai import contracts as c

from app.db.models import InterviewTurn


def question_position(
    question: c.Question, parent: InterviewTurn | None, *, interview_id: UUID, turn_no: int
) -> tuple[int, int | None]:
    if question.question_type == "main":
        return 1, None
    if (
        parent is None
        or str(parent.id) != question.parent_turn_id
        or parent.interview_session_id != interview_id
        or parent.persona != question.persona
        or parent.status != "answered"
        or not 1 <= parent.turn_no < turn_no
        or type(parent.depth) is not int
        or not 1 <= parent.depth < 9
        or parent.depth > parent.turn_no
    ):
        raise ValueError("question_parent_invalid")
    return parent.depth + 1, parent.turn_no
