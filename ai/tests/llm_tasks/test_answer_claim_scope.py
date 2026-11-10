"""일반 설계 판단을 코드 사실 판정으로 바꾸지 않고 생성 계약도 일치시킨다."""

import pytest

from devon_ai import contracts as c

PROMPT = c.PromptSpec("answer_analysis", "answer_analysis_v5@sol-check", "fixture", "fixture")


def test_general_reasoning_can_be_assessed_without_code_claims(kit, run):
    provider = kit.Provider(kit.analysis_output(claim_checks=[]))
    assert run(provider, prompt=PROMPT).succeeded
    request = provider.requests[0]
    assert request.schema_version == "5"
    variants = request.output_schema["properties"]["claim_checks"]["items"]["anyOf"]
    assert len(variants) == 1
    unverified = variants[0]["properties"]
    assert unverified["status"]["enum"] == ["unverified"]
    assert unverified["limitations"]["minItems"] == 1


def test_supported_claim_generation_requires_a_real_code_reference(kit, run):
    evidence = c.Evidence("ev-1", "repo-1", kit.REF, "file", "a.py", None, "code", None)
    provider = kit.Provider(kit.analysis_output())
    assert run(provider, context=kit.make_context(evidence=(evidence,)), prompt=PROMPT).succeeded
    variants = provider.requests[0].output_schema["properties"]["claim_checks"]["items"]["anyOf"]
    verified = next(
        v["properties"] for v in variants if "supported" in v["properties"]["status"]["enum"]
    )
    assert set(verified["status"]["enum"]) == {"supported", "partially_supported", "conflicting"}
    assert verified["evidence_refs"]["minItems"] == 1
    assert verified["evidence_refs"]["items"]["enum"] == ["ev-1"]


@pytest.mark.parametrize("status", ["supported", "partially_supported", "conflicting"])
def test_ungrounded_fact_status_is_still_a_nonretryable_semantic_failure(kit, run, status):
    provider = kit.Provider(
        kit.analysis_output(
            claim_checks=[
                {
                    "claim_text": "조회가 많아서",
                    "status": status,
                    "evidence_refs": [],
                    "limitations": ["일반적인 이해를 코드 관찰로 승격하지 않는다."],
                }
            ]
        )
    )
    result = run(provider, prompt=PROMPT)
    assert result.data is None and result.failure.stage == "semantic"
    assert len(provider.requests) == 1
