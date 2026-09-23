"""TXT / MD 텍스트 추출.

docs/layer-rules.md 1절 / task-09

표준 라이브러리만 쓴다. 인코딩이 확실하지 않아 utf-8 -> cp949 순으로 시도한다.
"""

from app.integrations.extract.base import (
    EXTRACT_ERROR_EMPTY,
    ExtractionResult,
    failed,
    truncate,
)
from app.shared.enums import DocumentExtractStatus

# 국내 사용자가 올리는 txt 는 cp949 인 경우가 드물지 않다.
_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")


def extract_plain_text(data: bytes, *, max_chars: int = 0) -> ExtractionResult:
    """TXT / MD 바이트에서 텍스트를 뽑는다.

    입력: 파일 바이트, max_chars(0 이면 자르지 않는다).
    출력: ExtractionResult.

    - 아는 인코딩으로 읽히면 succeeded
    - 전부 실패하면 깨진 글자를 남기고 partial 로 표시한다 (내용을 통째로 버리지 않는다)
    - 내용이 비어 있으면 empty_document
    """
    decoded: str | None = None
    for encoding in _ENCODINGS:
        try:
            decoded = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        break

    replaced = decoded is None
    if decoded is None:
        decoded = data.decode("utf-8", errors="replace")

    if not decoded.strip():
        return failed(EXTRACT_ERROR_EMPTY)

    text, is_truncated = truncate(decoded.strip(), max_chars)
    partial = is_truncated or replaced
    return ExtractionResult(
        text=text,
        status=DocumentExtractStatus.PARTIAL if partial else DocumentExtractStatus.SUCCEEDED,
        is_truncated=is_truncated,
    )
