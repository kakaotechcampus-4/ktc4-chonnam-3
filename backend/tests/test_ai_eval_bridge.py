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
                        "version": "fixture",
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
