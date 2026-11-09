import asyncio
import json
from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import report

PROMPT = c.PromptSpec("report", "report_v1", "fixture-model", "template")
LIMITS = c.CallLimits(1, 4096, 65536, 65536)
REF = "a" * 40


CONTRACT = c.QuestionContract("목적", (c.RequiredPoint("k", "내용"),), (), (), "평가 범위")


def turn(n, persona, follows=None, evidence=(), answer=None):
    answer = f"답변{n}" if answer is None else answer
    return c.ReportTurn(f"turn-{n}", persona, f"질문{n}", answer, follows, None, evidence, CONTRACT)


TOOL_ERROR = c.ToolResult("tool_error", (), (), ("조회 실패",), "tool_failed")
INPUT = c.ReportInput(
    (
        turn(1, "hr_manager"),
        turn(2, "tech_lead", evidence=("m1",)),
        turn(3, "domain_lead"),
        turn(4, "tech_lead", follows="turn-2"),
    ),
    (c.Evidence("m1", "repo-1", REF, "code", "build.gradle", None, "implementation redis", None),),
    (c.ReportToolResult("turn-3", TOOL_ERROR),),
)


def claim(turns=("turn-2",), evidence=()):
    return {"text": "관찰", "turn_refs": list(turns), "evidence_refs": list(evidence)}


def persona(name):
    return {
        "persona": name,
        "tags": ["Redis"],
        "strengths": [claim()],
        "improvements": [claim()],
        "practice_actions": [claim()],
        "limitations": [],
    }


EMPTY_SUMMARY = {key: [] for key in ("strengths", "gaps", "follow_ups", "practice_actions")}


def empty_persona(name, limitations=()):
    return {
        **persona(name),
        "strengths": [],
        "improvements": [],
        "practice_actions": [],
        "limitations": list(limitations),
    }


def output(**changes):
    raw = {
        "headline": "근거를 갖고 설명하는 지원자",
        "summary": {
            key: [claim()] for key in ("strengths", "gaps", "follow_ups", "practice_actions")
        },
        "persona_feedbacks": [persona(p) for p in c.NARRATIVE_PERSONAS],
    }
    raw.update(changes)
    return raw


@pytest.fixture
def run():
    def _run(provider, **options):
        source = options.pop("report_input", INPUT)
        args = {"prompt": PROMPT, "limits": LIMITS, "model_call": provider}
        args.update(options)
        return asyncio.run(report.write_narrative(source, **args))

    return _run


def test_valid_narrative_comes_back_checked_without_any_score(run, kit):
    result = run(kit.Provider(output()))
    assert result.succeeded
    assert "score" not in json.dumps(c.to_data(result.data), ensure_ascii=False).lower()


def test_only_limitations_is_a_narrative_that_admits_what_it_could_not_say(run, kit):
    only_limits = [
        empty_persona(p, ["근거 조회 실패로 서술하지 못함"]) for p in c.NARRATIVE_PERSONAS
    ]
    result = run(kit.Provider(output(summary=EMPTY_SUMMARY, persona_feedbacks=only_limits)))
    assert result.succeeded


def test_request_carries_follow_up_and_tool_status_but_no_score(run, kit):
    provider = kit.Provider(output())
    run(provider)
    request = provider.requests[0]
    assert request.schema_name == "ReportNarrative"
    turns = request.payload["turns"]
    assert turns[3]["follows"] == "turn-2" and turns[1]["follows"] is None
    assert turns[1]["evidence_refs"] == ["m1"] and turns[0]["evidence_refs"] == []
    assert request.payload["tool_results"][0]["result"]["status"] == "tool_error"
    assert "score" not in json.dumps(request.payload, ensure_ascii=False).lower()


@pytest.mark.parametrize(
    "options",
    [
        {"prompt": replace(PROMPT, task_name="report_score")},
        {"report_input": replace(INPUT, turns=())},
        {
            "report_input": replace(
                INPUT, turns=(turn(1, "hr_manager", follows="turn-2"), turn(2, "tech_lead"))
            )
        },
        {"max_attempts": 3},
    ],
    ids=["prompt", "no turns", "follows later turn", "attempts"],
)
def test_bad_input_never_reaches_the_model(run, kit, options):
    provider = kit.Provider(output())
    result = run(provider, **options)
    assert result.failure.error_code == "report_input_invalid"
    assert provider.requests == []


@pytest.mark.parametrize(
    ("raw", "stage"),
    [
        (output(scores=[{"key": "communication", "score": 80}]), "schema"),
        (output(headline="한 줄\n두 줄"), "semantic"),
        (output(persona_feedbacks=[persona("tech_lead"), persona("hr_manager")]), "semantic"),
        (
            output(
                summary={
                    key: [claim(turns=("turn-9",))]
                    for key in ("strengths", "gaps", "follow_ups", "practice_actions")
                }
            ),
            "semantic",
        ),
        ({k: v for k, v in output().items() if k != "summary"}, "schema"),
        (output(summary={**output()["summary"], "score": 80}), "schema"),
        (
            output(persona_feedbacks=[{**persona(p), "score": 80} for p in c.NARRATIVE_PERSONAS]),
            "schema",
        ),
        (
            output(summary={**output()["summary"], "strengths": [{**claim(), "score": 80}]}),
            "schema",
        ),
        (
            output(
                summary=EMPTY_SUMMARY,
                persona_feedbacks=[empty_persona(p) for p in c.NARRATIVE_PERSONAS],
            ),
            "semantic",
        ),
    ],
    ids=[
        "score field",
        "multiline headline",
        "missing persona",
        "unknown turn",
        "missing summary",
        "extra summary field",
        "extra persona field",
        "extra claim field",
        "nothing narrated",
    ],
)
def test_bad_model_output_is_a_typed_failure(run, kit, raw, stage):
    result = run(kit.Provider(raw))
    assert result.data is None
    assert result.failure.stage == stage


def test_a_model_call_that_skips_the_validator_is_checked_again(run, kit):
    other = replace(
        INPUT,
        turns=tuple(
            replace(t, turn_id=f"x-{t.turn_id}", follows=t.follows and f"x-{t.follows}")
            for t in INPUT.turns
        ),
    )
    other = replace(other, tool_results=())
    wrong = c.validate_narrative(
        c.decode(
            c.ReportNarrative,
            output(
                summary={
                    key: [claim(turns=("x-turn-2",))]
                    for key in ("strengths", "gaps", "follow_ups", "practice_actions")
                },
                persona_feedbacks=[
                    {
                        **persona(p),
                        "strengths": [claim(("x-turn-2",))],
                        "improvements": [claim(("x-turn-2",))],
                        "practice_actions": [claim(("x-turn-2",))],
                    }
                    for p in c.NARRATIVE_PERSONAS
                ],
            ),
        ),
        report_input=other,
    )

    async def skips_validator(request, validator):
        return c.ModelResult(wrong, None, (kit.metadata(),))

    assert run(skips_validator).failure.error_code == "report_invalid"


def test_a_model_call_returning_something_else_is_a_programming_error(run, kit):
    async def unchecked(request, validator):
        return c.ModelResult("not checked", None, (kit.metadata(),))

    with pytest.raises(TypeError):
        run(unchecked)
