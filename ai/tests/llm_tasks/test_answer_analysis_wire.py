"""v6의 상태 조합과 원문 ID는 표현만 변환하고 실제 판정은 바꾸지 않는다."""

from copy import deepcopy

import pytest

from devon_ai import contracts as c

PROMPT = c.PromptSpec("answer_analysis", "answer_analysis_v6@fixture", "fixture", "fixture")


def wire():
    return {
        "coverage_assessment": {
            "evaluation_status": "evaluated",
            "sufficiency": "partial",
            "covered_points": {
                "read_pattern": ["answer:0001"],
                "write_pattern": None,
                "cache_purpose": ["answer:0001"],
            },
            "missing_points": ["write_pattern"],
            "limitations": ["수정 특성은 설명되지 않았다."],
        },
        "technical_assessment": {
            "explanation": "조회 부하에 대한 설명",
            "quote_ids": ["answer:0001"],
            "evidence_refs": [],
            "limitations": [],
        },
        "contribution_scope": {
            "scope": "unknown",
            "quote_ids": [],
            "unknown_reason": "본인 역할은 언급되지 않았다.",
        },
        "claim_checks": [],
        "verification_requests": [],
        "external_queries": [],
    }


def test_v6_maps_original_units_and_unknown_reason_without_inventing_a_judgment(kit, run):
    provider = kit.Provider(wire())
    result = run(provider, prompt=PROMPT)
    assert result.succeeded
    actual = result.data.data
    assert actual.sufficiency == "partial" and actual.missing_points == ("write_pattern",)
    assert actual.covered_points[0].answer_quotes == (kit.ANSWER,)
    assert actual.technical_assessment.answer_quotes == (kit.ANSWER,)
    assert (
        actual.contribution_scope.scope == "unknown" and not actual.contribution_scope.answer_quotes
    )
    assert actual.limitations == ("수정 특성은 설명되지 않았다.", "본인 역할은 언급되지 않았다.")
    assert actual.needs_verification is False
    request = provider.requests[0]
    assert request.schema_version == "6"
    unit = request.payload["answer_units"][0]
    assert unit == {
        "id": "answer:0001",
        "start_char": 0,
        "end_char": len(kit.ANSWER),
        "text": kit.ANSWER,
    }
    assert "sufficiency" not in request.payload and "coverage_assessment" not in request.payload


def test_coverage_generation_has_fixed_question_keys_and_nested_state_branches(kit, run):
    provider = kit.Provider(wire())
    run(provider, prompt=PROMPT)
    schema = provider.requests[0].output_schema
    assert "anyOf" not in schema and "needs_verification" not in schema["properties"]
    variants = schema["properties"]["coverage_assessment"]["anyOf"]
    sufficient = next(
        v["properties"]
        for v in variants
        if v["properties"]["sufficiency"].get("enum") == ["sufficient"]
    )
    assert sufficient["missing_points"]["maxItems"] == 0
    points = sufficient["covered_points"]
    assert set(points["required"]) == {point.key for point in kit.make_contract().required_points}
    assert points["additionalProperties"] is False
    partial = next(
        v["properties"]
        for v in variants
        if v["properties"]["sufficiency"].get("enum") == ["partial"]
    )
    assert partial["missing_points"]["minItems"] == partial["limitations"]["minItems"] == 1
    assert "uniqueItems" not in partial["missing_points"]
    assert set(partial["missing_points"]["items"]["enum"]) == set(points["required"])


def test_actual_partial_with_every_key_covered_but_no_missing_point_is_not_repaired(kit, run):
    candidate = wire()
    candidate["coverage_assessment"]["covered_points"]["write_pattern"] = ["answer:0001"]
    candidate["coverage_assessment"]["missing_points"] = []
    provider = kit.Provider(candidate)
    result = run(provider, prompt=PROMPT)
    assert result.failure.stage == "semantic" and len(provider.requests) == 1


def test_actual_general_reasoning_is_not_promoted_to_a_supported_code_claim(kit, run):
    candidate = wire()
    candidate["claim_checks"] = [
        {
            "quote_id": "answer:0001",
            "status": "supported",
            "evidence_refs": [],
            "limitations": [],
        }
    ]
    provider = kit.Provider(candidate)
    result = run(provider, prompt=PROMPT)
    assert result.failure.stage == "semantic" and len(provider.requests) == 1


@pytest.mark.parametrize("second_status", ["supported", "conflicting"])
def test_one_source_unit_cannot_receive_multiple_claim_judgments(kit, run, second_status):
    candidate = wire()
    candidate["claim_checks"] = [
        {
            "quote_id": "answer:0001",
            "status": "supported",
            "evidence_refs": ["ev-1"],
            "limitations": [],
        },
        {
            "quote_id": "answer:0001",
            "status": second_status,
            "evidence_refs": ["ev-1"],
            "limitations": ["별도 사유"],
        },
    ]
    evidence = c.Evidence("ev-1", "repo-1", kit.REF, "file", "a.py", None, "code", None)
    provider = kit.Provider(candidate)
    result = run(provider, prompt=PROMPT, context=kit.make_context(evidence=(evidence,)))
    assert result.failure.stage == "semantic" and len(provider.requests) == 1


@pytest.mark.parametrize(
    "change", ["unknown_quote", "duplicate_quote", "blank_reason", "missing_key"]
)
def test_invalid_wire_is_not_silently_filled_or_corrected(kit, run, change):
    candidate = wire()
    if change == "unknown_quote":
        candidate["technical_assessment"]["quote_ids"] = ["fabricated"]
    elif change == "duplicate_quote":
        candidate["technical_assessment"]["quote_ids"] = ["answer:0001", "answer:0001"]
    elif change == "blank_reason":
        candidate["contribution_scope"]["unknown_reason"] = " "
    else:
        del candidate["coverage_assessment"]["covered_points"]["write_pattern"]
    provider = kit.Provider(candidate)
    assert not run(provider, prompt=PROMPT).succeeded


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5])
def test_legacy_versions_keep_the_flat_canonical_generation_shape(kit, run, version):
    provider = kit.Provider(kit.analysis_output())
    prompt = c.PromptSpec(
        "answer_analysis", f"answer_analysis_v{version}@fixture", "fixture", "fixture"
    )
    assert run(provider, prompt=prompt).succeeded
    request = provider.requests[0]
    assert request.schema_version == str(version)
    assert "coverage_assessment" not in request.output_schema["properties"]
    assert "answer_units" not in request.payload


def test_units_remain_bounded_and_cover_the_actual_tail_without_rewriting_it(kit, run):
    answer = " ".join(f"실제 문장 {i}." for i in range(150))
    provider = kit.Provider(wire())
    assert run(provider, prompt=PROMPT, answer=answer).succeeded
    units = provider.requests[0].payload["answer_units"]
    assert 1 <= len(units) <= 128
    assert units[-1]["end_char"] == len(answer)
    for unit in units:
        assert unit["text"] == answer[unit["start_char"] : unit["end_char"]]


def test_verification_is_derived_only_from_explicit_requests_and_quotes_restore_exactly(kit, run):
    candidate = deepcopy(wire())
    candidate["verification_requests"] = [
        {
            "claim_quote_id": "answer:0001",
            "purpose": "구현 원문 확인",
            "repository_id": "repo-1",
            "git_ref": kit.REF,
            "allowed_paths": ["a.py"],
        }
    ]
    provider = kit.Provider(candidate)
    result = run(
        provider, prompt=PROMPT, allowed_locations=frozenset({("repo-1", kit.REF, "a.py")})
    )
    assert result.succeeded and result.data.data.needs_verification
    assert result.data.data.verification_requests[0].claim_text == kit.ANSWER
