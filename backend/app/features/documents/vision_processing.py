"""읽지 못한 문서 영역만 Vision으로 보완하고 전사와 생성 설명을 구분한다."""

import json
import unicodedata
from dataclasses import replace

from app.features.documents.processing import _bounded_text
from app.integrations.extract.base import ExtractionBlock, ExtractionResult
from app.integrations.extract.github_urls import extract_github_full_names
from app.integrations.vision.elice import EliceVisionClient, VisionError
from app.shared.enums import DocumentExtractStatus


async def supplement_with_vision(
    data: bytes,
    mime_type: str,
    filename: str,
    native: ExtractionResult,
    client: EliceVisionClient,
    *,
    max_preview_chars: int,
) -> tuple[ExtractionResult, list[str]]:
    try:
        vision = await client.extract(data, mime_type, filename=filename)
        # 공급자 결과의 비표준 숫자 등이 원문 저장 전체를 깨뜨리지 않게 먼저 확인한다.
        json.dumps(vision.raw_result, allow_nan=False, ensure_ascii=False).encode("utf-8")
        _validate_storage_strings(vision.raw_result)
    except (VisionError, ValueError, UnicodeError, RecursionError) as exc:
        reason = exc.reason if isinstance(exc, VisionError) else "vision_metadata_invalid"
        return mark_vision_unavailable(native, reason), []
    nul_removed = any("\x00" in block.text for block in native.blocks)
    blocks = [replace(block, text=block.text.replace("\x00", "")) for block in native.blocks]
    if not blocks and (native.source_text or native.text):
        blocks.append(ExtractionBlock(native.source_text or native.text))
    seen = {
        (block.page, _normalized(part))
        for block in blocks
        for part in (block.text, *block.text.splitlines())
        if _normalized(part)
    }
    interpretations = []
    untranscribed = False
    for block in vision.blocks:
        if block.description and block.description.strip():
            interpretations.append(
                {
                    "page": block.page,
                    "element": block.element_index,
                    "description": block.description,
                    "coordinate": block.coordinate,
                    "label": block.label,
                }
            )
        if not block.content or not block.content.strip():
            # 생성 설명은 원문 전사로 보충할 수 없다. 해당 시각 영역의 한계를 남긴다.
            untranscribed = True
            continue
        content = block.content.replace("\x00", "")
        nul_removed = nul_removed or content != block.content
        identity = (block.page, _normalized(content))
        # 같은 페이지에 텍스트가 있어도 표·이미지 안의 새 전사를 버리지 않는다.
        if identity[1] and identity not in seen:
            seen.add(identity)
            blocks.append(
                ExtractionBlock(
                    content,
                    page=block.page,
                    coordinate=block.coordinate,
                    label=block.label,
                )
            )
    blocks.sort(key=lambda item: item.page or 0)
    text = "\n\n".join(block.text.strip() for block in blocks if block.text.strip())
    read_pages = {block.page for block in blocks if block.page is not None and block.text.strip()}
    limitations = list(dict.fromkeys(native.limitations + vision.limitations))
    if untranscribed:
        limitations.append("visual_regions_not_transcribed")
    if nul_removed:
        limitations.append("nul_characters_removed")
    partial = len(read_pages) < vision.page_count or bool(limitations)
    if partial:
        limitations.append("unread_document_regions")
    metadata: dict[str, object] = {
        "vision_job_id": vision.job_id,
        "vision_raw_result": vision.raw_result,
        "visual_interpretations": interpretations,
    }
    if not text:
        if interpretations:
            # 전사 원문이 없는 도식도 해석 자료로 남기되 텍스트 주장으로 만들지 않는다.
            return ExtractionResult(
                "",
                DocumentExtractStatus.PARTIAL,
                details={"pageCount": vision.page_count, "extractedPages": 0},
                limitations=tuple(limitations),
                source_text="",
                source_is_partial=True,
                source_metadata=metadata,
            ), []
        return ExtractionResult(
            "",
            DocumentExtractStatus.FAILED,
            error_code="empty_document",
            limitations=tuple(limitations),
            source_metadata=metadata,
        ), []
    preview = _bounded_text(text, max_preview_chars) if len(text) > max_preview_chars else text
    result = ExtractionResult(
        preview,
        DocumentExtractStatus.PARTIAL
        if partial or len(preview) < len(text)
        else DocumentExtractStatus.SUCCEEDED,
        is_truncated=len(preview) < len(text),
        details={"pageCount": vision.page_count, "extractedPages": len(read_pages)},
        blocks=tuple(blocks),
        limitations=tuple(limitations),
        source_text=text,
        source_is_partial=partial,
        source_metadata=metadata,
    )
    return result, extract_github_full_names(text)


def _normalized(text: str) -> str:
    """위치가 같은 동일 내용만 중복 제거하고 저장 원문 자체는 바꾸지 않는다."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def mark_vision_unavailable(native: ExtractionResult, reason: str) -> ExtractionResult:
    return replace(
        native,
        status=DocumentExtractStatus.PARTIAL if native.succeeded else native.status,
        source_is_partial=True,
        limitations=tuple(dict.fromkeys(native.limitations + (reason, "unread_document_regions"))),
    )


def _validate_storage_strings(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str) and "\x00" in current:
            raise ValueError("Invalid JSON storage character")
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
