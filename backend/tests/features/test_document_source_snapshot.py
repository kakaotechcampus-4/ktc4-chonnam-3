"""화면용 축약과 분리한 문서 원문·위치 보존을 검증한다."""

import hashlib

import pytest

from app.integrations.extract.base import ExtractionResult
from app.shared.enums import DocumentExtractStatus


def test_snapshot_preserves_full_text_and_original_file_version():
    from app.features.documents.source_snapshot import snapshot_document

    text = "첫 문단\n\n구현 설명\n" + "상세 설명\n" * 100
    result = ExtractionResult(text, DocumentExtractStatus.SUCCEEDED)
    snapshot = snapshot_document(b"original bytes", result, max_chars=10000)
    assert snapshot["text"] == text
    assert snapshot["source_hash"] == hashlib.sha256(b"original bytes").hexdigest()
    assert snapshot["text_hash"] == hashlib.sha256(text.encode()).hexdigest()
    assert snapshot["limitations"] == []


def test_claim_location_uses_actual_lines_including_blank_lines():
    from app.features.documents.source_snapshot import claim_location, snapshot_document

    result = ExtractionResult("프로젝트\n\n  직접 구현한 부분  \n", DocumentExtractStatus.SUCCEEDED)
    snapshot = snapshot_document(b"file", result, max_chars=10000)
    location = claim_location(snapshot, 1, "  직접 구현한 부분  ")
    assert location["start_line"] == location["end_line"] == 3
    assert location["text_hash"] == snapshot["text_hash"]
    with pytest.raises(ValueError, match="source"):
        claim_location(snapshot, 1, "모델이 바꾼 원문")


def test_snapshot_limit_marks_unread_tail_and_keeps_real_line_boundary():
    from app.features.documents.source_snapshot import snapshot_document

    result = ExtractionResult("first\nsecond\nthird", DocumentExtractStatus.SUCCEEDED)
    snapshot = snapshot_document(b"file", result, max_chars=10)
    assert snapshot["text"] == "first\n"
    assert "source_text_truncated" in snapshot["limitations"]
    assert snapshot["source_hash"] == hashlib.sha256(b"file").hexdigest()


def test_pdf_page_blocks_preserve_original_page_number():
    from app.features.documents.source_snapshot import claim_location, snapshot_document
    from app.integrations.extract.base import ExtractionBlock

    result = ExtractionResult(
        "page one\n\npage three",
        DocumentExtractStatus.PARTIAL,
        blocks=(
            ExtractionBlock("page one", page=1),
            ExtractionBlock("page three", page=3),
        ),
    )
    snapshot = snapshot_document(b"pdf", result, max_chars=10000)
    location = claim_location(snapshot, 1, "page three")
    assert location["page"] == 3
    assert location["start_line"] == 3
    assert "partial_extraction" in snapshot["limitations"]


@pytest.mark.parametrize("separator", ["\r", "\f", "\u2028", "\r\n", "\n"])
def test_mixed_line_separators_keep_original_bytes_and_page_coordinates(separator):
    from app.features.documents.source_snapshot import claim_location, snapshot_document
    from app.integrations.extract.base import ExtractionBlock

    text = "first" + separator + "second\nthird"
    result = ExtractionResult(
        text,
        DocumentExtractStatus.SUCCEEDED,
        blocks=(
            ExtractionBlock("first" + separator + "second", page=1),
            ExtractionBlock("third", page=2, coordinate=[1, 2, 3, 4]),
        ),
    )
    snapshot = snapshot_document(b"unaltered file", result, max_chars=1000)
    location = claim_location(snapshot, 2, "third")
    assert snapshot["blocks"][1]["start_line"] == 3
    assert location["page"] == 2 and location["coordinate"] == [1, 2, 3, 4]
    assert snapshot["text"] == text
    assert snapshot["text_hash"] == hashlib.sha256(text.encode()).hexdigest()


def test_legacy_lf_block_locations_are_not_relabelled_as_verified_pages():
    from copy import deepcopy

    from app.features.documents.source_snapshot import claim_location

    text = "A\fB\nC\nD\nE"
    snapshot = {
        "version": "document-source.v1",
        "text": text,
        "text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "blocks": [
            {"start_line": 1, "end_line": 2, "page": 1},
            {"start_line": 2, "end_line": 3, "page": 2},
            {"start_line": 4, "end_line": 4, "page": 3},
        ],
    }
    before = deepcopy(snapshot)
    location = claim_location(snapshot, 3, "D")
    assert location["start_line"] == 4
    assert "page" not in location
    assert "legacy_block_line_policy_unverified" in location["limitations"]
    assert snapshot == before
