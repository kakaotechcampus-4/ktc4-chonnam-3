"""텍스트와 이미지 표가 같은 페이지에 있는 문서의 보완 추출."""

import httpx
from pydantic import SecretStr

from app.features.documents.vision_processing import supplement_with_vision
from app.integrations.extract.base import ExtractionBlock, ExtractionResult
from app.integrations.vision.elice import EliceVisionClient, EliceVisionSettings
from app.shared.enums import DocumentExtractStatus


def native():
    return ExtractionResult(
        "Project title",
        DocumentExtractStatus.SUCCEEDED,
        details={"pageCount": 1, "extractedPages": 1},
        blocks=(ExtractionBlock("Project title", page=1),),
        source_text="Project title",
    )


def vision(elements, *, fail=False):
    def provider(request):
        if fail:
            return httpx.Response(503, json={"private": "provider detail"})
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "layout-job", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {"pages": [{"elements": elements}]},
            },
        )

    return EliceVisionClient(
        EliceVisionSettings(
            base_url="https://example.mlapi.run",
            api_key=SecretStr("test"),
            poll_interval_seconds=0.001,
        ),
        transport=httpx.MockTransport(provider),
    )


async def test_same_page_native_title_does_not_hide_ocr_table():
    client = vision(
        [
            {"label": "title", "content": "Project   title", "coordinate": [0, 0, 1, 1]},
            {
                "label": "table",
                "content": "Metric | Value\nLatency | 15ms",
                "coordinate": [1, 2, 3, 4],
            },
        ]
    )
    result, _ = await supplement_with_vision(
        b"pdf",
        "application/pdf",
        "portfolio.pdf",
        native(),
        client,
        max_preview_chars=1000,
    )
    assert result.source_text.count("Project") == 1
    assert "Latency | 15ms" in result.source_text
    assert result.blocks[1].page == 1
    assert result.blocks[1].coordinate == [1, 2, 3, 4]
    assert result.status is DocumentExtractStatus.SUCCEEDED


async def test_failed_layout_keeps_native_text_but_marks_unread_regions():
    result, _ = await supplement_with_vision(
        b"pdf",
        "application/pdf",
        "portfolio.pdf",
        native(),
        vision([], fail=True),
        max_preview_chars=1000,
    )
    assert result.text == result.source_text == "Project title"
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.source_is_partial is True
    assert "unread_document_regions" in result.limitations
    assert "provider detail" not in str(result)


async def test_description_only_figure_is_not_transcribed_source():
    result, _ = await supplement_with_vision(
        b"pdf",
        "application/pdf",
        "portfolio.pdf",
        native(),
        vision([{"label": "figure", "description": "AI described a deployment diagram"}]),
        max_preview_chars=1000,
    )
    assert result.source_text == "Project title"
    assert "AI described" not in result.text
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.source_metadata["visual_interpretations"][0]["description"].startswith("AI")


async def test_invalid_json_storage_character_keeps_safe_native_source():
    result, _ = await supplement_with_vision(
        b"pdf",
        "application/pdf",
        "portfolio.pdf",
        native(),
        vision([{"label": "text", "content": "unsafe\x00text"}]),
        max_preview_chars=1000,
    )
    assert result.source_text == "Project title"
    assert result.source_is_partial is True
    assert result.source_metadata == {}


async def test_visual_description_without_transcription_is_partial_input():
    empty = ExtractionResult("", DocumentExtractStatus.FAILED, error_code="no_text_layer")
    result, urls = await supplement_with_vision(
        b"image",
        "image/png",
        "diagram.png",
        empty,
        vision([{"label": "figure", "description": "AI described a deployment diagram"}]),
        max_preview_chars=1000,
    )
    assert result.status is DocumentExtractStatus.PARTIAL
    assert result.text == result.source_text == ""
    assert result.error_code is None
    assert result.source_is_partial is True
    assert result.source_metadata["visual_interpretations"]
    assert urls == []


async def test_no_transcription_or_description_remains_failed():
    empty = ExtractionResult("", DocumentExtractStatus.FAILED, error_code="no_text_layer")
    result, _ = await supplement_with_vision(
        b"image",
        "image/png",
        "diagram.png",
        empty,
        vision([{"label": "figure", "description": "   "}]),
        max_preview_chars=1000,
    )
    assert result.status is DocumentExtractStatus.FAILED
