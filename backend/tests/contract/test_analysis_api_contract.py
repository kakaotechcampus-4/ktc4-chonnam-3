"""분석 결과의 부분 실패 요약과 공개 API 계약을 함께 검증한다."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.features.analysis import run_schemas as schemas

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"
OPENAPI = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
SCHEMAS = OPENAPI["components"]["schemas"]
SUMMARY_FIELDS = {"analyzedCount", "failedCount", "failedRepositories"}
RUN_ID = "8a52f6eb-9130-44ee-828e-c7f14edb9041"
REPOSITORY_ID = "7767e11c-9ca4-4b68-8949-7014484c136c"


def _result_payload() -> dict[str, Any]:
    return {
        "runId": RUN_ID,
        "position": "Backend Developer",
        "companyName": None,
        "jdRequirements": [],
        "mentionedRepoCount": 0,
        "matchedRepoCount": 0,
        "analyzedCount": 2,
        "failedCount": 1,
        "failedRepositories": [{"repositoryId": REPOSITORY_ID, "errorCode": "llm_parse_failed"}],
        # 필터에서 숨겨진 저장소도 집계하므로 카드 개수와 집계가 같을 필요는 없다.
        "repositories": [],
    }


def test_openapi_requires_nonnegative_result_summary() -> None:
    result = SCHEMAS["AnalysisRunResultResponse"]

    assert SUMMARY_FIELDS <= set(result["required"])
    for name in ("analyzedCount", "failedCount"):
        assert result["properties"][name]["type"] == "integer"
        assert result["properties"][name]["minimum"] == 0


def test_openapi_failed_repository_has_only_identifier_and_error_code() -> None:
    result = SCHEMAS["AnalysisRunResultResponse"]
    failures = result["properties"]["failedRepositories"]
    assert failures["type"] == "array"
    item = SCHEMAS[failures["items"]["$ref"].rsplit("/", 1)[-1]]

    assert set(item["required"]) == {"repositoryId", "errorCode"}
    assert set(item["properties"]) == {"repositoryId", "errorCode"}
    for field in item["properties"].values():
        assert field["type"] == "string"
        assert not field.get("nullable", False)


def test_candidate_errors_and_page_validation_are_documented() -> None:
    operation = OPENAPI["paths"]["/analysis-runs/{runId}/candidates"]["get"]
    responses = operation["responses"]

    assert {"200", "202", "400", "401", "409", "410"} <= set(responses)
    assert "invalid_request" in responses["400"]["description"]
    assert "not_ready" in responses["409"]["description"]
    assert "candidate_page_failed" in responses["409"]["description"]
    assert "run_expired" in responses["410"]["description"]
    page = next(item for item in operation["parameters"] if item.get("name") == "page")
    assert page["required"] is True
    assert page["schema"] == {"type": "integer", "minimum": 1}


def test_result_serialization_matches_openapi_required_fields() -> None:
    result = schemas.AnalysisRunResultResponse.model_validate(_result_payload())
    payload = result.model_dump(mode="json")
    contract = SCHEMAS["AnalysisRunResultResponse"]

    assert set(payload) == set(contract["required"]) == set(contract["properties"])
    assert payload == _result_payload()
    assert result.analyzed_count == 2
    assert result.failed_count == 1
    assert payload["failedRepositories"] == [
        {"repositoryId": REPOSITORY_ID, "errorCode": "llm_parse_failed"}
    ]


@pytest.mark.parametrize("field", sorted(SUMMARY_FIELDS))
def test_result_summary_fields_cannot_be_omitted(field: str) -> None:
    payload = _result_payload()
    del payload[field]

    with pytest.raises(ValidationError):
        schemas.AnalysisRunResultResponse.model_validate(payload)


@pytest.mark.parametrize("field", ["analyzedCount", "failedCount"])
def test_result_counts_cannot_be_negative(field: str) -> None:
    payload = _result_payload()
    payload[field] = -1

    with pytest.raises(ValidationError):
        schemas.AnalysisRunResultResponse.model_validate(payload)


@pytest.mark.parametrize("field", ["repositoryId", "errorCode"])
def test_failed_repository_requires_nonnull_fields(field: str) -> None:
    payload = _result_payload()
    payload["failedRepositories"][0][field] = None

    with pytest.raises(ValidationError):
        schemas.AnalysisRunResultResponse.model_validate(payload)


@pytest.mark.parametrize("nested", [False, True])
def test_result_does_not_accept_private_token_fields(nested: bool) -> None:
    payload = _result_payload()
    target = payload["failedRepositories"][0] if nested else payload
    target["accessToken"] = "must-not-be-exposed"

    with pytest.raises(ValidationError):
        schemas.AnalysisRunResultResponse.model_validate(payload)
