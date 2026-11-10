"""화면용 축약문과 분리하여 재현 가능한 추출 원문과 위치를 보존한다."""

import hashlib
from bisect import bisect_right
from typing import Any

from app.integrations.extract.base import ExtractionResult
from app.shared.enums import DocumentExtractStatus


def snapshot_document(
    data: bytes,
    result: ExtractionResult,
    *,
    max_chars: int,
    method: str = "native_text",
) -> dict[str, Any]:
    if max_chars <= 0:
        raise ValueError("Source text limit must be positive")
    text = result.source_text if result.source_text is not None else result.text
    limitations = list(result.limitations)
    if len(text) > max_chars:
        # 줄을 임의로 절단한 내용을 완전한 원문 근거처럼 사용하지 않는다.
        boundary = text.rfind("\n", 0, max_chars + 1)
        text = text[: boundary + 1] if boundary >= 0 else ""
        limitations.append("source_text_truncated")
    if result.source_is_partial is True or (
        result.source_is_partial is None and result.status is DocumentExtractStatus.PARTIAL
    ):
        limitations.append("partial_extraction")
    blocks: list[dict[str, Any]] = []
    # 원문을 바꾸지 않고 AI와 같은 splitlines 기준의 문자 offset을 사용한다.
    line_starts: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        line_starts.append(offset)
        offset += len(line)
    cursor = 0
    for index, block in enumerate(result.blocks):
        content = block.text.strip()
        start = text.find(content, cursor) if content else -1
        if start < 0:
            limitations.append("block_outside_preserved_text")
            continue
        first = bisect_right(line_starts, start)
        blocks.append(
            {
                "index": index,
                "page": block.page,
                "start_line": first,
                "end_line": bisect_right(line_starts, start + len(content) - 1),
                "coordinate": block.coordinate,
                "label": block.label,
            }
        )
        cursor = start + len(content)
    return {
        "version": "document-source.v1",
        "line_numbering": "splitlines.v1",
        "source_hash": hashlib.sha256(data).hexdigest(),
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "method": method,
        "metadata": result.source_metadata,
        "text": text,
        "blocks": blocks,
        "limitations": list(dict.fromkeys(limitations)),
    }


def claim_location(snapshot: dict[str, Any], paragraph_no: int, source_line: str) -> dict[str, Any]:
    """AI의 비어 있지 않은 줄 순번을 보존한 원문의 실제 줄로 복원한다."""
    text = snapshot.get("text")
    if type(text) is not str or type(paragraph_no) is not int or paragraph_no < 0:
        raise ValueError("Invalid claim source")
    lines = [(number, line) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    if paragraph_no >= len(lines) or lines[paragraph_no][1] != source_line:
        raise ValueError("Claim source does not match preserved text")
    number, _ = lines[paragraph_no]
    location: dict[str, Any] = {
        "text_hash": snapshot["text_hash"],
        "start_line": number,
        "end_line": number,
    }
    if snapshot.get("line_numbering") != "splitlines.v1" and any(
        value in text.replace("\r\n", "") for value in "\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
    ):
        # 과거 LF 기반 좌표는 새 기준으로 검증한 페이지인 것처럼 재사용하지 않는다.
        location["limitations"] = ["legacy_block_line_policy_unverified"]
        return location
    for block in snapshot.get("blocks", []):
        if block["start_line"] <= number <= block["end_line"]:
            location.update(page=block.get("page"), coordinate=block.get("coordinate"))
            break
    return location
