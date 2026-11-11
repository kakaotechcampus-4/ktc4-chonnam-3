"""v7은 주장 범위만 정확히 복원하고 판정·v6 원문 해석을 바꾸지 않는다."""

from copy import deepcopy

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks.answer_analysis import decode_analysis_output

PROMPT = c.PromptSpec("answer_analysis", "answer_analysis_v7@fixture", "fixture", "fixture")
ANSWER = (
    "현재 TTL은 30초이고 자동 연장은 꺼져 있으며, 저는 보관 방식을 바꾸겠습니다. "
    "다른 문장은 별도의 원문입니다."
)


def output(claims=()):
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
            "limitations": ["쓰기 특성은 설명되지 않았다."],
        },
        "technical_assessment": {
            "explanation": "현재 설정 진술과 변경 제안을 구분한다.",
            "quote_ids": ["answer:0001"],
            "evidence_refs": [],
            "limitations": [],
        },
        "contribution_scope": {
            "scope": "unknown",
            "quote_ids": [],
            "unknown_reason": "개인 기여는 미확인이다.",
        },
        "claim_checks": list(claims),
        "verification_requests": [],
        "external_queries": [],
    }


def claim(excerpt="현재 TTL은 30초", **changes):
    value = {
        "quote_id": "answer:0001",
        "claim_excerpt": excerpt,
        "status": "supported",
        "evidence_refs": ["ev-1"],
        "limitations": [],
    }
    value.update(changes)
    return value


def context(kit):
    evidence = c.Evidence(
        "ev-1",
        "repo-1",
        kit.REF,
        "file",
        "settings.py",
        None,
        "ttl = 30\nrenewal_enabled = True",
        None,
    )
    return kit.make_context(evidence=(evidence,))


def test_v7_keeps_distinct_fact_excerpts_from_one_unit_and_original_judgments(kit, run):
    raw = output(
        (
            claim(),
            claim(
                "자동 연장은 꺼져 있으며", status="conflicting", limitations=["코드 설정은 True다."]
            ),
        )
    )
    preserved = deepcopy(raw)
    provider = kit.Provider(raw)
    result = run(provider, prompt=PROMPT, context=context(kit), answer=ANSWER)
    assert result.succeeded
    assert [(item.claim_text, item.status) for item in result.data.data.claim_checks] == [
        ("현재 TTL은 30초", "supported"),
        ("자동 연장은 꺼져 있으며", "conflicting"),
    ]
    assert raw == provider.output == preserved
    assert "저는 보관 방식을 바꾸겠습니다" not in result.data.data.claim_checks[0].claim_text


def test_v7_schema_requires_excerpt_but_v6_does_not(kit, run):
    providers = []
    for version in (6, 7):
        provider = kit.Provider(output())
        prompt = c.PromptSpec(
            "answer_analysis", f"answer_analysis_v{version}@fixture", "fixture", "fixture"
        )
        assert run(provider, prompt=prompt, answer=ANSWER).succeeded
        request = provider.requests[0]
        assert request.schema_version == str(version)
        variants = request.output_schema["properties"]["claim_checks"]["items"]["anyOf"]
        assert all(
            ("claim_excerpt" in variant["required"]) == (version == 7) for variant in variants
        )
        providers.append(provider)
    assert providers[0].requests[0].payload == providers[1].requests[0].payload


@pytest.mark.parametrize(
    "change",
    [
        "unknown_unit",
        "other_unit",
        "blank",
        "empty",
        "altered",
        "missing_field",
        "duplicate_pair",
    ],
)
def test_v7_rejects_invalid_claim_without_deleting_it_or_repairing_status(kit, run, change):
    raw = output((claim(),))
    selected = raw["claim_checks"][0]
    if change == "unknown_unit":
        selected["quote_id"] = "fabricated"
    elif change == "other_unit":
        selected["claim_excerpt"] = "다른 문장은 별도의 원문입니다."
    elif change == "blank":
        selected["claim_excerpt"] = " \n\t"
    elif change == "empty":
        selected["claim_excerpt"] = ""
    elif change == "altered":
        selected["claim_excerpt"] = "현재  TTL은 30초"
    elif change == "missing_field":
        del selected["claim_excerpt"]
    else:
        raw["claim_checks"].append(
            {**selected, "status": "partially_supported", "limitations": ["다른 판정"]}
        )
    preserved = deepcopy(raw)
    provider = kit.Provider(raw)
    result = run(provider, prompt=PROMPT, context=context(kit), answer=ANSWER)
    assert not result.succeeded and len(provider.requests) == 1
    expected_stage = "schema" if change in {"blank", "empty", "missing_field"} else "semantic"
    assert result.failure.stage == expected_stage
    assert provider.output == preserved


def test_v7_preserves_partial_support_for_a_genuine_combined_fact_claim(kit, run):
    raw = output(
        (
            claim(
                "현재 TTL은 30초이고 자동 연장은 꺼져 있으며",
                status="partially_supported",
                limitations=["TTL은 일치하지만 연장 설정 진술은 다르다."],
            ),
        )
    )
    actual = run(kit.Provider(raw), prompt=PROMPT, context=context(kit), answer=ANSWER)
    assert actual.succeeded
    [checked] = actual.data.data.claim_checks
    assert checked.status == "partially_supported"
    assert checked.limitations == ("TTL은 일치하지만 연장 설정 진술은 다르다.",)


def test_v7_does_not_require_a_claim_check_for_a_proposal(kit, run):
    provider = kit.Provider(output())
    result = run(
        provider, prompt=PROMPT, context=context(kit), answer="저는 보관 방식을 바꾸겠습니다."
    )
    assert result.succeeded and result.data.data.claim_checks == ()


def test_v7_restoration_is_version_bound_and_v6_keeps_whole_units(kit, run):
    raw = output((claim(),))
    canonical = decode_analysis_output(
        raw,
        prompt_version="answer_analysis_v7@fixture",
        schema_version="7",
        answer_text=ANSWER,
        contract=kit.make_contract(),
    )
    assert canonical.claim_checks[0].claim_text == "현재 TTL은 30초"
    with pytest.raises(c.ContractError):
        decode_analysis_output(
            raw,
            prompt_version="answer_analysis_v7@fixture",
            schema_version="6",
            answer_text=ANSWER,
            contract=kit.make_contract(),
        )
    legacy = output((claim(),))
    del legacy["claim_checks"][0]["claim_excerpt"]
    provider = kit.Provider(legacy)
    v6 = c.PromptSpec("answer_analysis", "answer_analysis_v6@fixture", "fixture", "fixture")
    restored = run(provider, prompt=v6, context=context(kit), answer=ANSWER)
    assert restored.succeeded
    assert restored.data.data.claim_checks[0].claim_text == ANSWER.split(". ")[0] + "."
    legacy["claim_checks"].append({**legacy["claim_checks"][0], "status": "conflicting"})
    assert not run(kit.Provider(legacy), prompt=v6, context=context(kit), answer=ANSWER).succeeded
