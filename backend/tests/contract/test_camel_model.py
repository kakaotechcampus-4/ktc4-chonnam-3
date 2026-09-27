"""CamelModel 직렬화 계약과 error envelope 모양.

docs/layer-rules.md 4절·5절 / task-04

"response 에 snake_case key 가 새지 않는다" 가 이 파일의 핵심이다.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.core.errors import AppError
from app.shared.enums import Reason
from app.shared.schema import CamelModel, CamelResponse

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"


class _Sample(CamelResponse):
    """여러 단어 필드로 camelCase 변환을 확인한다."""

    run_id: str
    estimated_seconds: int | None = None
    failure_reason: str | None = None


def _load_api_error_schema() -> dict[str, Any]:
    with OPENAPI_PATH.open(encoding="utf-8") as stream:
        spec: dict[str, Any] = yaml.safe_load(stream)
    schema: dict[str, Any] = spec["components"]["schemas"]["ApiError"]
    return schema


# openapi type -> Python 타입. bool 은 int 의 하위 타입이라 integer 에서 따로 막는다.
_OPENAPI_TYPES: dict[str, type] = {"string": str, "integer": int, "object": dict}


def _assert_matches_openapi_types(error: dict[str, Any], properties: dict[str, Any]) -> None:
    """envelope 의 각 필드 값이 openapi properties 의 type 과 맞는지 본다."""
    for key, value in error.items():
        expected = properties[key]["type"]
        assert expected in _OPENAPI_TYPES, f"대조표에 없는 openapi type: {expected}"
        assert isinstance(value, _OPENAPI_TYPES[expected]), (key, expected, value)
        if expected == "integer":
            assert not isinstance(value, bool), (key, value)


def test_response_has_no_snake_case_key() -> None:
    dumped = _Sample(run_id="r1", estimated_seconds=20).model_dump()

    assert all("_" not in key for key in dumped), dumped
    assert set(dumped) == {"runId", "estimatedSeconds", "failureReason"}


def test_response_json_is_camel_case() -> None:
    """model_dump_json() 도 by_alias 없이 camelCase 여야 한다."""
    payload = _Sample(run_id="r1").model_dump_json()

    assert '"runId"' in payload
    assert "run_id" not in payload


def test_request_accepts_camel_case() -> None:
    parsed = _Sample.model_validate({"runId": "r1", "estimatedSeconds": 3})

    assert parsed.run_id == "r1"
    assert parsed.estimated_seconds == 3


def test_internal_code_can_use_snake_case_names() -> None:
    """populate_by_name — service 계층이 파이썬 이름으로 생성할 수 있어야 한다."""
    assert _Sample(run_id="r1").run_id == "r1"


def test_unknown_key_is_rejected() -> None:
    """계약에 없는 키를 조용히 받아들이지 않는다."""
    with pytest.raises(ValidationError):
        _Sample.model_validate({"runId": "r1", "surpriseField": 1})


def test_camel_model_is_usable_as_request_base() -> None:
    class _Request(CamelModel):
        posting_url: str

    assert _Request.model_validate({"postingUrl": "https://x"}).posting_url == "https://x"


def test_error_envelope_matches_openapi_api_error() -> None:
    """AppError.to_envelope() 이 openapi ApiError 모양과 맞는지 본다."""
    schema = _load_api_error_schema()
    envelope = AppError(Reason.INVALID_REPOSITORY, details={"repositoryId": "x"}).to_envelope()

    assert set(envelope) == set(schema["required"]) == {"error"}

    error_schema = schema["properties"]["error"]
    error = envelope["error"]
    assert isinstance(error, dict)
    # 계약이 요구하는 키가 전부 있고, 계약에 없는 키를 새로 만들지 않는다.
    assert set(error_schema["required"]) <= set(error)
    assert set(error) <= set(error_schema["properties"])
    _assert_matches_openapi_types(error, error_schema["properties"])


def test_error_envelope_retry_after_is_camel_case() -> None:
    error_schema = _load_api_error_schema()["properties"]["error"]
    envelope = AppError(Reason.NOT_READY, retry_after=3).to_envelope()
    error = envelope["error"]

    assert isinstance(error, dict)
    assert "retryAfter" in error
    assert "retry_after" not in error
    _assert_matches_openapi_types(error, error_schema["properties"])
