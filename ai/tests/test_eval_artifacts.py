"""내부 관찰 자료가 임의 검수 필드나 무근거 Claim 통로가 되지 않게 검사한다."""

import copy

import pytest
from eval_artifacts import validate_artifacts


def artifact():
    return {
        "schema_version": "validated-report-claims.v1",
        "claims": [
            {
                "section": "strengths",
                "persona": "tech_lead",
                "claim_index": 0,
                "text": "observed answer",
                "turn_refs": ["2"],
                "evidence_refs": [],
            }
        ],
    }


@pytest.mark.parametrize("invalid", ["review_metadata", "no_basis", "unknown_version"])
def test_rejects_unrecognized_or_unreferenced_artifacts(invalid):
    value = artifact()
    if invalid == "review_metadata":
        value["claims"][0]["review"] = {"verdict": "accept"}
    elif invalid == "no_basis":
        value["claims"][0]["turn_refs"] = []
    else:
        value["schema_version"] = "unknown"
    with pytest.raises(ValueError):
        validate_artifacts(value)


def test_preserves_actual_text_and_references_in_an_independent_copy():
    value = artifact()
    before = copy.deepcopy(value)
    checked = validate_artifacts(value)
    checked["claims"][0]["turn_refs"].append("3")
    assert value == before
