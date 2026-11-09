"""REST 원본과 WS 확장 문서가 실제 오류·중복 단위를 잃지 않는지 검사한다."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ws_error_details_are_optional_not_a_new_reason_or_required_payload():
    document = (ROOT / "frontend/docs/api-spec.md").read_text(encoding="utf-8")
    row = next(
        line
        for line in document.splitlines()
        if line.startswith("| `error` |") and "`recoverable`" in line
    )
    assert "`details`" in row and "선택" in row
    assert "empty_transcript" in document
