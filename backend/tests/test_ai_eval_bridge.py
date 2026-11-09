"""실제 AI 진입점을 주입된 모델 호출로 실행하는 평가 도구 회귀."""

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from devon_ai import contracts as c

TEST_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TEST_REPO_ROOT / "ai" / "evals"))

from eval_runner import ExecutionError  # noqa: E402

from scripts.ai_eval_bridge import ServiceExecutor, prepare  # noqa: E402


def first_context():
    return c.Context(
        "eval",
        None,
        1,
        9,
        (),
        ("hr_manager",),
        (),
        (),
        (),
        None,
        (),
        (),
        c.ContextLimits(2, 0, "test"),
    )


def contract():
    return c.QuestionContract(
        "역할 확인", (c.RequiredPoint("role", "맡은 역할"),), (), (), "역할 설명"
    )


def payload():
    return {
        "service_task": "director",
        "service_input": {"context": json.loads(json.dumps(asdict(first_context())))},
    }


@pytest.mark.parametrize("task_timeout", [None, 13])
async def test_director_bridge_calls_the_real_planner_and_independent_review_without_eval_labels(
    task_timeout,
):
    seen = []

    async def model_call(request, validator):
        seen.append(request)
        raw = (
            {
                "question": {
                    "persona": "hr_manager",
                    "text": "맡은 역할은 무엇인가요?",
                    "topic_code": "role",
                    "question_contract": json.loads(json.dumps(asdict(contract()))),
                    "evidence_refs": [],
                    "jd_requirement_ids": [],
                },
                "intent": "main",
                "reason_summary": "역할 확인",
            }
            if request.payload["operation"] == "plan"
            else {
                "plan_valid": True,
                "context_valid": True,
                "wording_valid": True,
                "contract_matches": True,
                "safe_alternative": True,
                "reason_summary": "checked",
            }
        )
        attempt = c.AttemptMetadata(1, "fixture", "fixture-model", "director_v2", "1", 1, 4, 5)
        return c.ModelResult(validator(raw), None, (attempt,))

    executor = ServiceExecutor(
        {"director": c.PromptSpec("director", "director_v2", "fixture-model", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: model_call,
        **(
            {"task_limits": {"director": c.CallLimits(task_timeout, 1024, 65536, 65536)}}
            if task_timeout
            else {}
        ),
    )
    result = await executor("question", payload())
    assert len(seen) == 2 and len(result.attempts) == 2
    assert all(request.limits.timeout_seconds == (task_timeout or 5) for request in seen)
    assert result.output["question"]["text"] == "맡은 역할은 무엇인가요?"
    assert not any(
        key in json.dumps([item.payload for item in seen])
        for key in ("grader_controls", "expectation", "source_group_id")
    )


async def test_shorthand_case_does_not_invent_a_preanswer_contract_or_a_git_sha():
    executor = ServiceExecutor({}, c.CallLimits(5, 1024, 65536, 65536), lambda: None)
    with pytest.raises(ExecutionError, match="explicit_service_input_required"):
        await executor(
            "question",
            {"question": "draft", "latest_analysis": {"missing_points": ["after-answer"]}},
        )


async def test_unknown_payload_metadata_is_rejected_before_any_model_call():
    def forbidden():
        pytest.fail("must reject the input before a model call")

    executor = ServiceExecutor({}, c.CallLimits(5, 1024, 65536, 65536), forbidden)
    invalid = payload()
    invalid["expectation"] = {"allowed": ["leaked answer"]}
    with pytest.raises(ExecutionError, match="service_envelope"):
        await executor("question", invalid)


async def test_dry_run_validates_typed_inputs_without_calling_a_provider():
    def forbidden():
        pytest.fail("dry-run must not call the model")

    executor = ServiceExecutor(
        {"director": c.PromptSpec("director", "director_v2", "m", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        forbidden,
        dry_run=True,
    )
    result = await executor("question", payload())
    assert result.validated_only and result.attempts == ()


async def test_dry_run_rejects_an_unsupported_director_version_without_a_model_call():
    def forbidden():
        pytest.fail("invalid dry-run must not call the model")

    executor = ServiceExecutor(
        {"director": c.PromptSpec("director", "future-fixture-version", "m", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        forbidden,
        dry_run=True,
    )
    with pytest.raises(ExecutionError, match="director_schema"):
        await executor("question", payload())


def test_report_bridge_rejects_missing_requirements_before_service_execution():
    # 빈 목록과 미기록을 구분한다. 평가 경로도 운영 리포트의 필수 입력을 생략하지 않는다.
    with pytest.raises(ExecutionError, match="contract_schema"):
        prepare("report", {"service_task": "report", "service_input": {"rubrics": {}, "turns": []}})


async def test_answer_bridge_runs_actual_t3_with_the_original_preanswer_contract():
    question = c.Question("hr_manager", "맡은 역할은 무엇인가요?", "role", contract(), (), ())
    context = replace(
        first_context(), current_turn_id="turn-1", current_question_contract=contract()
    )
    sent = []

    async def call(request, validator):
        sent.append(request)
        raw = asdict(
            c.AnswerAnalysis(
                "evaluated",
                "insufficient",
                (),
                ("role",),
                c.TechnicalAssessment("자료 없음", (), (), ("구현 미확인",)),
                c.ContributionScope("unknown", ()),
                (),
                False,
                (),
                ("기여 미확인",),
            )
        )
        return c.ModelResult(
            validator(json.loads(json.dumps(raw))),
            None,
            (c.AttemptMetadata(1, "fixture", "m", "answer_analysis_v2", "2", 1, 4, 5),),
        )

    executor = ServiceExecutor(
        {"answer_analysis": c.PromptSpec("answer_analysis", "answer_analysis_v2", "m", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: call,
    )
    result = await executor(
        "evidence",
        {
            "service_task": "answer_analysis",
            "service_input": {
                "context": json.loads(json.dumps(asdict(context))),
                "question": json.loads(json.dumps(asdict(question))),
                "turn_id": "turn-1",
                "answer_text": "모르겠습니다",
            },
        },
    )
    assert result.output["missing_points"] == ("role",)
    assert sent[0].payload["question"]["question_contract"]["required_points"][0]["key"] == "role"
