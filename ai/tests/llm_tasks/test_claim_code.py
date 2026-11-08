"""문서의 주장과 실제 코드 구간만 대조하며 개인 기여를 확정하지 않는다."""

import asyncio

from devon_ai import contracts as c
from devon_ai.llm_tasks.claim_code import ClaimForComparison, compare_claims

PROMPT = c.PromptSpec("claim_code", "claim_code_v1", "fixture", "Compare")
LIMITS = c.CallLimits(1, 512, 65536, 65536)


def claim(kind="implementation"):
    return ClaimForComparison(
        "claim-1", kind, "API uses a cache", "API uses a cache", "a" * 64, "L1"
    )


def evidence():
    return c.Evidence(
        evidence_id="evidence-1",
        repository_id="repo-1",
        git_ref="b" * 40,
        source_kind="file",
        path="app.py",
        metadata_key=None,
        content="cache.get(key)",
        tool_name=None,
        start_line=1,
        end_line=1,
    )


def output(**changes):
    item = {
        "claim_id": "claim-1",
        "status": "consistent",
        "reason": "Cache lookup is present.",
        "evidence_quotes": [{"evidence_id": "evidence-1", "quote": "cache.get(key)"}],
        "limitations": [],
    }
    return {"comparisons": [{**item, **changes}]}


def run(raw, *, claims=None, evidences=None):
    requests = []

    async def model(request, validator):
        requests.append(request)
        attempts = (c.AttemptMetadata(1, "fixture", "fixture", PROMPT.version, "1", 1, 1, 1),)
        try:
            return c.ModelResult(validator(raw), None, attempts)
        except c.ContractError as error:
            return c.ModelResult(
                None, c.CallFailure(error.stage, "llm_failed", "Rejected"), attempts
            )

    result = asyncio.run(
        compare_claims(
            claims or (claim(),),
            (evidence(),) if evidences is None else evidences,
            prompt=PROMPT,
            limits=LIMITS,
            model_call=model,
        )
    )
    return result, requests


def test_comparison_preserves_code_and_document_versions_in_input():
    result, requests = run(output())
    assert result.succeeded
    assert requests[0].payload["claims"][0]["source_version"] == "a" * 64
    assert requests[0].payload["evidences"][0]["git_ref"] == "b" * 40
    assert result.data[0].status == "consistent"
    assert "not_personal_contribution_evidence" in result.data[0].limitations


def test_unread_or_invented_evidence_cannot_confirm_or_conflict():
    for quotes in [
        [],
        [{"evidence_id": "other", "quote": "cache.get(key)"}],
        [{"evidence_id": "evidence-1", "quote": "cache.set(key)"}],
    ]:
        result, _ = run(output(evidence_quotes=quotes))
        assert result.failure.stage == "semantic"


def test_model_must_return_each_requested_claim_once():
    for raw in [{"comparisons": []}, {"comparisons": output()["comparisons"] * 2}]:
        result, _ = run(raw)
        assert result.failure.stage == "semantic"


def test_no_code_is_unverified_without_model_call():
    result, requests = run(output(), evidences=())
    assert result.succeeded and result.data[0].status == "unverified"
    assert "code_evidence_unavailable" in result.data[0].limitations
    assert requests == []


def test_personal_role_and_outcome_are_unverified_without_model_call():
    for kind in ["role", "outcome"]:
        result, requests = run(output(), claims=(claim(kind),))
        assert result.data[0].status == "unverified" and requests == []
        assert "personal_role_or_outcome_not_verifiable_from_code" in result.data[0].limitations


def test_unverified_result_requires_a_reason_for_the_limit():
    result, _ = run(output(status="unverified", evidence_quotes=[], limitations=[]))
    assert result.failure.stage == "semantic"


def test_malformed_status_is_a_schema_failure():
    result, _ = run(output(status=[]))
    assert result.failure.stage == "schema"
