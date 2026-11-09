import asyncio
from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import report_score
from devon_ai.report_scores import compute_scores

PROMPT = c.PromptSpec("report_score", "report_score_v1", "fixture-model", "template")
LIMITS = c.CallLimits(1, 2048, 65536, 65536)
CONTRACT = c.QuestionContract("목적", (c.RequiredPoint("k", "내용"),), (), (), "평가 범위")
PERSONAS = [
    "hr_manager", "tech_lead", "tech_lead", "domain_lead", "tech_lead",
    "tech_lead", "domain_lead", "tech_lead", "tech_lead",
]  # fmt: skip
TURNS = tuple(
    c.ScoreTurn(f"turn-{n}", persona, f"질문{n}", f"답변{n}", CONTRACT)
    for n, persona in enumerate(PERSONAS, 1)
)
RUBRIC = tuple(
    c.RubricLevel(key, level, f"{key} {level}단계")
    for key in ("project_understanding", "technical_reasoning", "problem_solving",
                "communication", "contribution_clarity", "company_job_fit")
    for level in range(5)
)  # fmt: skip


def output(level=2, **changes):
    judgments = [
        {"turn_id": t.turn_id, "key": key, "level": level}
        for t in TURNS
        for key in c.SCORE_CANDIDATE_KEYS[t.persona]
    ]
    return {"judgments": judgments, **changes}


@pytest.fixture
def run():
    def _run(provider, **options):
        turns = options.pop("turns", TURNS)
        args = {"rubric": RUBRIC, "prompt": PROMPT, "limits": LIMITS, "model_call": provider}
        args.update(options)
        return asyncio.run(report_score.judge_scores(turns, **args))

    return _run


def test_valid_judgments_come_back_checked_and_can_be_scored(run, kit):
    provider = kit.Provider(output(3))
    result = run(provider)
    assert result.succeeded
    assert compute_scores(result.data).total_score == 70
    assert len(provider.requests) == 1


def test_request_carries_candidate_keys_rubric_and_contract_but_not_persona(run, kit):
    provider = kit.Provider(output())
    run(provider)
    request = provider.requests[0]
    assert request.schema_name == "ScoreJudgments"
    turn = request.payload["turns"][3]  # turn-4, domain_lead
    assert turn["candidate_keys"] == ["company_job_fit", "communication"]
    assert turn["question_contract"]["evaluation_scope"] == "평가 범위"
    assert "persona" not in turn
    assert len(request.payload["rubric"]) == 30


@pytest.mark.parametrize(
    "options",
    [
        {"prompt": replace(PROMPT, task_name="answer_analysis")},
        {"turns": ()},
        {"turns": TURNS + (TURNS[0],)},
        {"rubric": RUBRIC[:-1]},
        {"rubric": RUBRIC + (RUBRIC[0],)},
        {"max_attempts": 3},
    ],
    ids=["prompt", "no turns", "duplicate turn", "missing rubric", "duplicate rubric", "attempts"],
)
def test_bad_input_never_reaches_the_model(run, kit, options):
    provider = kit.Provider(output())
    result = run(provider, **options)
    assert result.failure.error_code == "report_score_input_invalid"
    assert provider.requests == []


@pytest.mark.parametrize(
    ("raw", "stage"),
    [
        ({**output(), "total_score": 80}, "schema"),
        (
            {"judgments": [{**output()["judgments"][0], "score": 80}, *output()["judgments"][1:]]},
            "schema",
        ),
        ({"judgments": [{"turn_id": "turn-1", "key": "communication", "level": 9}]}, "schema"),
        ({"judgments": output()["judgments"][:-1]}, "semantic"),
        ({"judgments": output()["judgments"] * 2}, "semantic"),
        (output("not_applicable"), "semantic"),
    ],
    ids=[
        "extra field",
        "extra judgment field",
        "bad level",
        "missing pair",
        "duplicates",
        "nothing scorable",
    ],
)
def test_bad_model_output_is_a_typed_failure_not_a_score(run, kit, raw, stage):
    result = run(kit.Provider(raw))
    assert result.data is None
    assert result.failure.stage == stage


def test_a_model_call_that_skips_the_validator_is_checked_again(run, kit):
    other = tuple(replace(t, turn_id=f"x-{t.turn_id}") for t in TURNS)
    wrong = c.validate_score_judgments(
        c.decode(
            c.ScoreJudgments,
            {
                "judgments": [
                    {"turn_id": t.turn_id, "key": key, "level": 2}
                    for t in other
                    for key in c.SCORE_CANDIDATE_KEYS[t.persona]
                ]
            },
        ),
        turns=other,
    )

    async def skips_validator(request, validator):
        return c.ModelResult(wrong, None, (kit.metadata(),))

    result = run(skips_validator)
    assert result.failure.error_code == "report_score_invalid"


def test_a_model_call_returning_something_else_is_a_programming_error(run, kit):
    async def unchecked(request, validator):
        return c.ModelResult("not checked", None, (kit.metadata(),))

    with pytest.raises(TypeError):
        run(unchecked)


def test_linked_jd_requirements_reach_the_request_as_reference_only(run, kit):
    requirement = c.LinkedRequirement("jd-1", "required", "Redis 운영 경험")
    turns = tuple(
        c.ScoreTurn(
            t.turn_id,
            t.persona,
            t.question,
            t.answer,
            t.question_contract,
            jd_requirement_ids=(requirement.id,),
            jd_requirements=(requirement,),
        )
        if t.turn_id == "turn-4"
        else t
        for t in TURNS
    )
    provider = kit.Provider(output())
    assert run(provider, turns=turns).succeeded
    sent = provider.requests[0].payload["turns"]
    assert sent[3]["jd_requirements"] == [
        {
            "id": "jd-1",
            "category": "required",
            "text": "Redis 운영 경험",
        }
    ]
    assert sent[0]["jd_requirements"] == []
