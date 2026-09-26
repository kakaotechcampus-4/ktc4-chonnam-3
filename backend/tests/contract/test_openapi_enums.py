"""openapi.yaml 의 enum 과 app/shared/enums.py 를 대조한다.

spec/shared/contracts/openapi.yaml / task-04

계약에 enum 값이 추가·삭제되면 이 테스트가 먼저 깨진다.
한쪽만 고치고 배포되는 것을 막는 것이 목적이다.
"""

import enum
import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.shared import enums as app_enums

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"

# openapi 에 대응 schema 가 없는 Python enum.
# Reason 은 ApiError.error.reason 이 자유 문자열이라 openapi 에 값 목록이 없다
# (원본은 backend/docs/error-reasons.md). tests/test_errors.py 가 따로 검증한다.
PYTHON_ONLY_ENUMS = {"Reason"}


def _load_openapi() -> dict[str, Any]:
    with OPENAPI_PATH.open(encoding="utf-8") as stream:
        loaded: dict[str, Any] = yaml.safe_load(stream)
    return loaded


def _openapi_enums() -> dict[str, list[str]]:
    """openapi components.schemas 에서 enum 인 것만 뽑는다. 출력: {이름: 값 목록}."""
    schemas: dict[str, Any] = _load_openapi()["components"]["schemas"]
    return {
        name: schema["enum"]
        for name, schema in schemas.items()
        if isinstance(schema, dict) and "enum" in schema
    }


def _python_enums() -> dict[str, type[enum.Enum]]:
    """app/shared/enums.py 의 Enum 클래스. 출력: {클래스 이름: 클래스}."""
    return {
        name: obj
        for name, obj in inspect.getmembers(app_enums, inspect.isclass)
        if issubclass(obj, enum.Enum) and obj.__module__ == app_enums.__name__
    }


OPENAPI_ENUMS = _openapi_enums()


def test_openapi_actually_has_enums() -> None:
    """경로가 틀려 빈 dict 를 비교하고 통과하는 상황을 막는다."""
    assert OPENAPI_PATH.exists(), f"openapi.yaml 을 찾지 못했다: {OPENAPI_PATH}"
    assert len(OPENAPI_ENUMS) >= 10, OPENAPI_ENUMS


@pytest.mark.parametrize("schema_name", sorted(OPENAPI_ENUMS))
def test_every_openapi_enum_has_python_counterpart(schema_name: str) -> None:
    python_enums = _python_enums()

    assert schema_name in python_enums, (
        f"openapi 의 {schema_name} 에 대응하는 enum 이 app/shared/enums.py 에 없다"
    )


@pytest.mark.parametrize("schema_name", sorted(OPENAPI_ENUMS))
def test_enum_values_match_openapi(schema_name: str) -> None:
    python_enum = _python_enums()[schema_name]
    expected = OPENAPI_ENUMS[schema_name]
    actual = [member.value for member in python_enum]

    assert sorted(actual) == sorted(expected), (
        f"{schema_name} 값이 다르다. openapi={sorted(expected)} python={sorted(actual)}"
    )


def test_no_extra_python_enum_without_contract() -> None:
    """계약에 없는 enum 을 조용히 늘리지 않는다. 의도한 것이면 PYTHON_ONLY_ENUMS 에 적는다."""
    extra = set(_python_enums()) - set(OPENAPI_ENUMS) - PYTHON_ONLY_ENUMS

    assert not extra, f"openapi 에 없는 enum: {sorted(extra)}"


def test_task_04_fixed_enums_are_exact() -> None:
    """task-04 가 문서에 못 박은 4개는 순서까지 고정한다."""
    assert [m.value for m in app_enums.RunStatus] == ["running", "completed", "failed"]
    assert [m.value for m in app_enums.StepKey] == [
        "doc_extract",
        "repo_select",
        "repo_detail",
        "jd_fetch",
        "jd_extract",
        "repo_analyze",
        "match_score",
    ]
    assert [m.value for m in app_enums.Persona] == ["tech_lead", "hr_manager", "domain_lead"]
    assert [m.value for m in app_enums.DocumentExtractStatus] == [
        "succeeded",
        "partial",
        "failed",
    ]
