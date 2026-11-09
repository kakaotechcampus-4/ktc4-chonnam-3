from dataclasses import replace

import pytest

from devon_ai import contracts as c

CONTRACT = c.QuestionContract("목적", (c.RequiredPoint("k", "내용"),), (), (), "평가 범위")
PERSONAS = [
    "hr_manager", "tech_lead", "tech_lead", "domain_lead", "tech_lead",
    "tech_lead", "domain_lead", "tech_lead", "tech_lead",
]  # fmt: skip


def turns():
    return tuple(
        c.ScoreTurn(f"turn-{n}", persona, "질문", "답변", CONTRACT)
        for n, persona in enumerate(PERSONAS, 1)
    )


def judgments(level=2, drop=(), extra=()):
    items = [
        c.ScoreJudgment(t.turn_id, key, level)
        for t in turns()
        for key in c.SCORE_CANDIDATE_KEYS[t.persona]
    ]
    items = [i for i in items if (i.turn_id, i.key) not in drop]
    return c.ScoreJudgments(tuple(items + list(extra)))


def check(candidate, turn_list=None):
    return c.validate_score_judgments(candidate, turns=turn_list or turns())


def test_full_judgments_pass_and_serialize():
    checked = check(judgments())
    # hr 1턴 x 2 key + tech 6턴 x 4 key + domain 2턴 x 2 key
    assert len(c.to_data(checked)["judgments"]) == 2 + 24 + 4


def test_not_applicable_is_allowed_while_each_key_keeps_a_scored_turn():
    candidate = judgments(drop={("turn-1", "communication")})
    candidate = c.ScoreJudgments(
        tuple(
            c.ScoreJudgment(j.turn_id, j.key, "not_applicable")
            if (j.turn_id, j.key) == ("turn-2", "communication")
            else j
            for j in candidate.judgments
        )
        + (c.ScoreJudgment("turn-1", "communication", 3),)
    )
    check(candidate)


@pytest.mark.parametrize(
    "bad",
    [
        judgments(drop={("turn-2", "technical_reasoning")}),
        judgments(extra=(c.ScoreJudgment("turn-2", "company_job_fit", 2),)),
        judgments(extra=(c.ScoreJudgment("turn-2", "technical_reasoning", 3),)),
        judgments(extra=(c.ScoreJudgment("turn-99", "communication", 2),)),
    ],
    ids=["missing", "non-candidate key", "duplicate", "unknown turn"],
)
def test_wrong_pairs_are_semantic_failures(bad):
    with pytest.raises(c.ContractError) as error:
        check(bad)
    assert error.value.stage == "semantic"


def test_a_key_with_no_scored_turn_is_rejected_not_defaulted():
    # company_job_fit의 유일한 후보 턴(turn-4, turn-7)을 모두 not_applicable로 만든다.
    candidate = c.ScoreJudgments(
        tuple(
            c.ScoreJudgment(j.turn_id, j.key, "not_applicable") if j.key == "company_job_fit" else j
            for j in judgments().judgments
        )
    )
    with pytest.raises(c.ContractError, match="unscorable key"):
        check(candidate)


@pytest.mark.parametrize("level", [5, -1, True, "3", None])
def test_bad_levels_are_schema_failures(level):
    with pytest.raises(c.ContractError) as error:
        c.ScoreJudgment("turn-1", "communication", level)
    assert error.value.stage == "schema"


def test_decode_rejects_an_unknown_score_key():
    raw = {"judgments": [{"turn_id": "turn-1", "key": "totalScore", "level": 2}]}
    with pytest.raises(c.ContractError):
        c.decode(c.ScoreJudgments, raw)


def test_a_turn_list_without_a_persona_for_a_key_cannot_be_scored():
    only_tech = tuple(t for t in turns() if t.persona == "tech_lead")
    candidate = c.ScoreJudgments(
        tuple(
            c.ScoreJudgment(t.turn_id, key, 2)
            for t in only_tech
            for key in c.SCORE_CANDIDATE_KEYS[t.persona]
        )
    )
    with pytest.raises(c.ContractError, match="unscorable key"):
        check(candidate, only_tech)


def test_rubric_level_range():
    c.RubricLevel("communication", 0, "text")
    with pytest.raises(c.ContractError):
        c.RubricLevel("communication", 5, "text")


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_an_unanswered_turn_cannot_receive_a_positive_level(level):
    turn_list = tuple(replace(t, answer=None) if t.turn_id == "turn-4" else t for t in turns())
    candidate = c.ScoreJudgments(
        tuple(
            replace(j, level=level) if j.turn_id == "turn-4" else j for j in judgments().judgments
        )
    )
    with pytest.raises(c.ContractError) as error:
        check(candidate, turn_list)
    assert error.value.stage == "semantic"


@pytest.mark.parametrize("level", [0, "not_applicable"])
def test_an_unanswered_turn_preserves_zero_or_not_applicable_without_rewriting(level):
    turn_list = tuple(replace(t, answer=None) if t.turn_id == "turn-4" else t for t in turns())
    candidate = c.ScoreJudgments(
        tuple(
            replace(j, level=level) if j.turn_id == "turn-4" else j for j in judgments().judgments
        )
    )
    assert check(candidate, turn_list).data == candidate
