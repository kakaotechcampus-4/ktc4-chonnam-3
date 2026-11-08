    original = await run_cases(
        [case],
        saved_executor,
        metadata={"dataset": cli.dataset_metadata(dataset)},
        bindings=bindings,
    )
    previous = tmp_path / "original.json"
    previous.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    before = previous.read_bytes()
    monkeypatch.setattr(cli, "load_cases", lambda path: [case])
    monkeypatch.setattr(cli, "Settings", lambda **kwargs: SimpleNamespace(require_llm=llm))
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(require_llm=llm))

    def forbidden_service(*args, **kwargs):
        raise AssertionError("rejudge must not instantiate service executor")

    monkeypatch.setattr(cli, "ServiceExecutor", forbidden_service)
    sent = []

    def handle(request):
        sent.append(request)
        return response(
            {"verdict": "ambiguous", "reason_summary": "limited", "criterion_results": []}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        actual = cli.call_model

        async def invoke(request, validator, **kwargs):
            kwargs["http_client"] = http
            return await actual(request, validator, **kwargs)

        monkeypatch.setattr(cli, "call_model", invoke)
        result = await cli.execute(
            args(
                cases=dataset,
                manifest=dataset / "manifest.json",
                approved_only=False,
                rejudge_results=previous,
                llm_judge=True,
                max_judge_attempts=1,
                env_file=tmp_path / "mock.env",
            )
        )
    assert len(sent) == 1 and previous.read_bytes() == before
    assert result["summary"]["service_model_calls"] == 0
    assert result["summary"]["rejudged_outputs"] == 1
    assert result["cases"][0]["output"] == {"saved": "candidate"}
    assert result["metadata"]["rejudge_source_sha256"] == hashlib.sha256(before).hexdigest()
    assert result["metadata"]["grader"]["prompt_version"] == "evaluation-judge-v2"


def test_manifest_records_and_validates_optional_task_limits(tmp_path):
    (tmp_path / "prompt.md").write_text("fixture", encoding="utf-8")
    source = {
        "prompts": [
            {
                "task_name": "director",
                "version": "v1",
                "model": "fixture",
                "template_path": "prompt.md",
            }
        ],
        "limits": asdict(llm().call_limits()),
        "task_limits": {"director": {"timeout_seconds": 13}},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    _, _, metadata = cli.load_manifest(path)
    assert metadata["task_limits"]["director"]["timeout_seconds"] == 13
    source["task_limits"]["director"]["timeout_seconds"] = -1
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError):
        cli.load_manifest(path)
