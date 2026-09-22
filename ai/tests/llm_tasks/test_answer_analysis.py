import pytest

from devon_ai import contracts as c


def test_confirmed_answer_retains_wire_fields_without_a_submission_identifier():
    answer = c.decode(c.SubmittedAnswer, {"type": "answer", "turn": 2, "text": "모르겠습니다"})
    assert answer.turn == 2 and answer.text == "모르겠습니다"


@pytest.mark.parametrize(
    "patch",
    [
        {"type": "draft"},
        {"turn": 0},
        {"turn": 10},
        {"turn": True},
        {"turn": "2"},
        {"text": " "},
        {"text": None},
        {"clientSubmissionId": "not-allowed"},
    ],
)
def test_invalid_submission_is_rejected(patch):
    with pytest.raises(c.ContractError):
        c.decode(c.SubmittedAnswer, dict({"type": "answer", "turn": 2, "text": "답변"}, **patch))
