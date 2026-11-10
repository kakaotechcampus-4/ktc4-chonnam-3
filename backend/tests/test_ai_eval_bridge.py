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


@pytest.mark.parametrize("include_trace,invalid_ref", [(False, False), (True, False), (True, True)])
async def test_report_bridge_runs_actual_score_and_narrative_tasks_and_public_form(
    include_trace, invalid_ref
):
    seen = []
    personas = ("hr_manager", "tech_lead", "domain_lead")
    keys = c.NARRATIVE_PERSONAS
    all_keys = {key for values in c.SCORE_CANDIDATE_KEYS.values() for key in values}
    source = {
        "requirements": [],
        "rubrics": {
            key: {str(level): f"rubric {key} {level}" for level in range(5)} for key in all_keys
        },
        "turns": [
            {
                "turn_no": n,
                "persona": persona,
                "question": "역할?",
                "answer": "답변",
                "question_contract": json.loads(json.dumps(asdict(contract()))),
                "evidences": [],
            }
            for n, persona in enumerate(personas, 1)
        ],
    }

    async def call(request, validator):
        seen.append(request)
        raw = (
            {
                "judgments": [
                    {"turn_id": str(n), "key": key, "level": 2}
                    for n, persona in enumerate(personas, 1)
                    for key in c.SCORE_CANDIDATE_KEYS[persona]
                ]
            }
            if request.prompt.task_name == "report_score"
            else {
                "headline": "면접 관찰",
                "summary": {
                    key: [
                        {
                            "text": "확인한 역할 설명",
                            "turn_refs": ["99" if invalid_ref else "1"],
                            "evidence_refs": [],
                        }
                    ]
                    if include_trace and key == "strengths"
                    else []
                    for key in ("strengths", "gaps", "follow_ups", "practice_actions")
                },
                "persona_feedbacks": [
                    {
                        "persona": persona,
                        "tags": ["role"],
                        "strengths": [],
                        "improvements": [],
                        "practice_actions": [],
                        "limitations": ["관찰 범위 제한"],
                    }
                    for persona in keys
                ],
            }
        )
        return c.ModelResult(
            validator(raw),
            None,
            (c.AttemptMetadata(1, "fixture", "m", request.prompt.version, "1", 1, 4, 5),),
        )

    prompts = {
        task: c.PromptSpec(task, f"{task}_v1", "m", "fixture")
        for task in ("report", "report_score")
    }
    execution = ServiceExecutor(prompts, c.CallLimits(5, 1024, 65536, 65536), lambda: call)(
        "report", {"service_task": "report", "service_input": source}
    )
    if invalid_ref:
        with pytest.raises(ExecutionError, match="service_contract_rejected"):
            await execution
        return
    result = await execution
    assert {request.prompt.task_name for request in seen} == {"report_score", "report"}
    assert len(result.output["scores"]) == 6 and result.output["totalScore"] == 45
    assert "validated_artifacts" not in result.output
    assert result.artifacts["schema_version"] == "validated-report-claims.v1"
    assert result.artifacts["claims"] == (
        [
            {
                "section": "summary.strengths",
                "persona": None,
                "claim_index": 0,
                "text": "확인한 역할 설명",
                "turn_refs": ["1"],
                "evidence_refs": [],
            }
        ]
        if include_trace
        else []
    )
    assert "turn 1" not in result.output["summary"]


async def test_verification_component_uses_no_prompt_or_model_factory(monkeypatch):
    from eval_cases import load_cases

    source = next(
        case
        for case in load_cases(TEST_REPO_ROOT / "ai/evals/service_regression")
        if case.case_id == "q-0007"
    ).model_input()
    source["service_task"] = "director_verification"

    def forbidden():
        pytest.fail("the pure controller must not create a model call")

    monkeypatch.setattr("httpx.AsyncClient", forbidden)
    monkeypatch.setattr("scripts.ai_eval_bridge.run_director", forbidden)

    result = await ServiceExecutor({}, c.CallLimits(5, 1024, 65536, 65536), forbidden)(
        "question", source
    )
    assert result.attempts == ()
    assert result.output["execution_scope"] == "verification_decision_only"
    assert result.output["decision"]["next_step"] == "retrieve"
    assert result.output["tool_io_executed"] is result.output["next_director_executed"] is False
    del source["service_input"]["answer_analysis"]
    with pytest.raises(ExecutionError, match="checked_answer_analysis_required"):
        await ServiceExecutor({}, c.CallLimits(5, 1024, 65536, 65536), forbidden)(
            "question", source
        )


async def test_cli_gateway_global_budget_limits_actual_http_attempts():
    import httpx

    from scripts.run_ai_evaluation import ModelAttemptBudget
    from tests.agents.director_helpers import response, settings

    sent = []

    def handler(req):
        sent.append(req)
        return response({"ok": True})

    request = c.ModelRequest(
        c.PromptSpec("director", "fixture", "m", "fixture"),
        {},
        "fixture",
        "1",
        {"type": "object"},
        c.CallLimits(5, 1024, 65536, 65536),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        budget = ModelAttemptBudget(1, settings(), http_client=http)
        call = budget.factory()
        first = await call(request, lambda raw: raw)
        second = await call(request, lambda raw: raw)
    assert first.failure is None and first.data == {"ok": True}
    assert second.failure.stage == "budget" and len(sent) == 1


def test_cli_dry_run_writes_reproducible_diagnostics_without_an_api_key(tmp_path):
    import os
    import subprocess

    backend = Path(__file__).resolve().parents[1]
    suite = tmp_path / "cases"
    for folder in ("inputs", "expectations"):
        (suite / folder).mkdir(parents=True)
    (suite / "inputs" / "q-9999.v1.json").write_text(
        json.dumps(
            {
                "case_id": "q-9999",
                "version": 1,
                "control": {
                    "kind": "question",
                    "split": "dev",
                    "source_group_id": "synthetic-9999",
                    "synthetic": True,
                },
                "payload": payload(),
            }
        ),
        encoding="utf-8",
    )
    (suite / "expectations" / "q-9999.v1.json").write_text(
        json.dumps(
            {
                "case_id": "q-9999",
                "version": 1,
                "allowed": [],
                "forbidden": [],
                "grader_controls": [],
                "review": {
                    "status": "unreviewed",
                    "author": None,
                    "reviewer": None,
                    "reviewed_at": None,
                    "pending_notes": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "prompt.md").write_text("fixture prompt", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "prompts": [
                    {
                        "task_name": "director",
                        "version": "director_v2",
                        "model": "fixture",
                        "template_path": "prompt.md",
                    }
                ],
                "limits": asdict(c.CallLimits(5, 1024, 65536, 65536)),
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_ai_evaluation",
            "--cases",
            str(suite),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
        cwd=backend,
        env={**os.environ, "OPENAI_API_KEY": "", "PROXY_TOKEN": ""},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["cases"][0]["status"] == "validated_only"
    assert saved["summary"]["quality_denominator"] == 0
    assert len(saved["metadata"]["working_source_sha256"]) == 64
    assert saved["metadata"]["prompts"][0]["model"] == "fixture"


async def test_service_examples_are_executable_inputs_but_not_approved_quality_cases():
    from eval_cases import load_cases

    examples = load_cases(TEST_REPO_ROOT / "ai/evals/service_examples")

    def forbidden():
        pytest.fail("input validation must not call the provider")

    prompts = {
        task: c.PromptSpec(
            task, f"{task}_v3" if task == "director" else f"{task}_v2", "fixture", "fixture"
        )
        for task in ("director", "answer_analysis", "report", "report_score")
    }
    executor = ServiceExecutor(
        prompts, c.CallLimits(5, 1024, 65536, 65536), forbidden, dry_run=True
    )
    assert {case.kind for case in examples} == {"question", "evidence", "report"}
    for case in examples:
        assert case.expectation["review"]["status"] == "unreviewed"
        assert (await executor(case.kind, case.model_input())).validated_only
