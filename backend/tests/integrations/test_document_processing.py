"""기존 추출기와 연결되는 본문 URL 보존·정리·길이 축약 정책."""

import importlib

import pytest

from app.integrations.extract.base import DocumentFormat
from app.shared.enums import DocumentExtractStatus
from tests.integrations.test_extract import build_docx, build_pdf


def process(data: bytes, document_format=DocumentFormat.TXT, max_chars=120):
    assert importlib.util.find_spec("app.features.documents"), "Document processing is missing"
    module = importlib.import_module("app.features.documents.processing")
    return module.process_document(data, document_format, max_chars=max_chars)


def test_truncation_keeps_end_links_and_prioritizes_url_context_and_project_heading():
    source = (
        "Unrelated biography.\n" * 30
        + "# Project DEVON\nBuilt an interview service.\n"
        + "Unrelated employment.\n" * 30
        + "Repository implementation:\nhttps://github.com/alice/end.git/tree/main?x=1\n"
    )
    result, urls = process(source.encode(), max_chars=150)

    assert urls == ["alice/end"]
    assert len(result.text) <= 150
    assert "# Project DEVON" in result.text
    assert "Repository implementation:" in result.text
    assert "https://github.com/alice/end.git/tree/main?x=1" in result.text
    assert result.text.index("# Project DEVON") < result.text.index("Repository implementation:")
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.is_truncated is True
    assert process(source.encode(), max_chars=150) == (result, urls)


def test_nul_cleanup_is_partial_and_does_not_lose_normalized_urls():
    result, urls = process(b"Hello\x00 world github.com/alice/project\x00")
    assert result.text == "Hello world github.com/alice/project"
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.is_truncated is False
    assert urls == ["alice/project"]


def test_nul_only_document_is_failed_after_cleanup():
    result, urls = process(b"\x00\x00")
    assert result.status is DocumentExtractStatus.FAILED
    assert result.error_code == "empty_document"
    assert urls == []


def test_processing_preserves_upstream_partial_without_truncation():
    result, urls = process(b"Portfolio \xff github.com/alice/project")
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.is_truncated is False
    assert "\ufffd" in result.text
    assert urls == ["alice/project"]


@pytest.mark.parametrize("max_chars", [1, 10, 120])
def test_all_urls_survive_even_when_text_budget_cannot_fit_them(max_chars):
    source = "github.com/alice/first\n" + "Filler.\n" * 100 + "github.com/alice/last"
    result, urls = process(source.encode(), max_chars=max_chars)
    assert urls == ["alice/first", "alice/last"]
    assert len(result.text) <= max_chars


@pytest.mark.parametrize(
    ("document_format", "data", "expected"),
    [
        (
            DocumentFormat.PDF,
            build_pdf("Portfolio https://github.com/alice/pdf.git/tree/main"),
            ["alice/pdf"],
        ),
        (
            DocumentFormat.DOCX,
            build_docx(["Portfolio", "https://github.com/alice/docx/issues/2"]),
            ["alice/docx"],
        ),
    ],
    ids=["pdf", "docx"],
)
@pytest.mark.parametrize("max_chars", [20, 120])
def test_processing_retains_pdf_and_docx_body_urls(document_format, data, expected, max_chars):
    result, urls = process(data, document_format, max_chars=max_chars)
    assert urls == expected
    assert len(result.text) <= max_chars
    assert result.is_truncated is (max_chars == 20)
    expected_status = (
        DocumentExtractStatus.PARTIAL if max_chars == 20 else DocumentExtractStatus.SUCCEEDED
    )
    assert result.status is expected_status


def test_nonpositive_text_budget_is_rejected():
    with pytest.raises(ValueError):
        process(b"text", max_chars=0)
