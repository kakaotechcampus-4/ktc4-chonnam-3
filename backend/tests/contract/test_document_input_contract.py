"""공개 문서 입력 계약이 실제 역할과 용량 제한을 빠뜨리지 않는지 확인한다."""

from pathlib import Path

import yaml

from app.core.config import Settings

OPENAPI = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"


def _contract():
    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def test_preview_declares_both_document_roles_and_legacy_default():
    operation = _contract()["paths"]["/documents/preview"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    role = schema["properties"]["docType"]
    assert role["type"] == "string"
    assert set(role["enum"]) == {"portfolio", "cover_letter"}
    assert role["default"] == "portfolio"
    assert schema["required"] == ["file"]


def test_preview_publishes_the_actual_role_specific_byte_limits():
    operation = _contract()["paths"]["/documents/preview"]["post"]
    assert operation["x-max-file-bytes-by-doc-type"] == {
        "portfolio": Settings.model_fields["max_upload_bytes_portfolio"].default,
        "cover_letter": Settings.model_fields["max_upload_bytes_cover_letter"].default,
    }


def test_run_declares_selected_cover_letter_without_requiring_either_document():
    schema = _contract()["components"]["schemas"]["CreateAnalysisRunRequest"]
    assert schema["required"] == ["postingUrl"]
    letter = schema["properties"]["coverLetterDocumentId"]
    assert letter["type"] == "string"
    assert letter["format"] == "uuid"
    assert "documentId" in schema["properties"]


def test_document_contract_distinguishes_native_and_optional_vision_formats():
    operation = _contract()["paths"]["/documents/preview"]["post"]
    assert operation["x-native-file-extensions"] == ["pdf", "docx", "txt", "md"]
    assert operation["x-vision-file-extensions"] == ["png", "jpg", "jpeg", "ppt", "pptx"]
