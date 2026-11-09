"""T3의 코드 근거 ID와 문서·비교·외부 자료 ID는 같은 참조 공간이 아니다."""

import pytest

from devon_ai import contracts as c


def supplemental():
    return c.SupplementalSource(
        "claim-1",
        "document_claim",
        "문서에 적힌 주장",
        "document:1:line=1",
        "a" * 64,
        ("document_claim_unverified",),
    )


def reference_schemas(request):
    properties = request.output_schema["properties"]
    return (
        properties["technical_assessment"]["properties"]["evidence_refs"],
        properties["claim_checks"]["items"]["properties"]["evidence_refs"],
    )


def test_payload_and_schema_limit_evidence_refs_to_registered_code_evidence(kit, run):
    evidence = c.Evidence("ev-1", "repo-1", kit.REF, "file", "a.py", None, "code", None)
    fetched = c.Evidence("ev-tool", "repo-1", kit.REF, "file", "b.py", None, "code", "read_file")
    context = kit.make_context(evidence=(evidence,), supplemental_sources=(supplemental(),))
    provider = kit.Provider(kit.analysis_output())
    assert run(
        provider,
        context=context,
        tool_results=(c.ToolResult("found", (fetched,), ("b.py",), (), None),),
        prompt=c.PromptSpec("answer_analysis", "answer_analysis_v4", "fixture", "fixture"),
    ).succeeded
    request = provider.requests[0]
    assert request.payload["allowed_evidence_refs"] == ["ev-1", "ev-tool"]
    assert request.schema_version == "4"
    for schema in reference_schemas(request):
        assert schema["items"]["enum"] == ["ev-1", "ev-tool"]
        assert "claim-1" not in schema["items"]["enum"]
    assert request.payload["supplemental_sources"][0]["source_id"] == "claim-1"


def test_only_supplemental_sources_requires_empty_evidence_ref_arrays(kit, run):
    provider = kit.Provider(kit.analysis_output())
    assert run(provider, context=kit.make_context(supplemental_sources=(supplemental(),))).succeeded
    request = provider.requests[0]
    assert request.payload["allowed_evidence_refs"] == []
    for schema in reference_schemas(request):
        assert schema["maxItems"] == 0


@pytest.mark.parametrize("field", ["technical", "claim"])
def test_supplemental_source_id_remains_a_semantic_failure_without_retry(kit, run, field):
    output = kit.analysis_output()
    if field == "technical":
        output["technical_assessment"]["evidence_refs"] = ["claim-1"]
    else:
        output["claim_checks"] = [
            {
                "claim_text": "조회가 많아서",
                "status": "unverified",
                "evidence_refs": ["claim-1"],
                "limitations": ["미검증 문서 주장"],
            }
        ]
    provider = kit.Provider(output)
    result = run(provider, context=kit.make_context(supplemental_sources=(supplemental(),)))
    assert result.failure.stage == "semantic" and len(provider.requests) == 1
