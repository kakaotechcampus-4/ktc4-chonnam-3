"""PDF 텍스트 추출 (자소서 / 포트폴리오).

docs/layer-rules.md 1절 / task-09

텍스트 레이어가 있는 PDF 만 지원한다. 스캔 이미지 PDF 는 추출 실패다 — OCR 은 범위 밖이다.
"""

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.integrations.extract.base import (
    EXTRACT_ERROR_CORRUPTED,
    EXTRACT_ERROR_NO_TEXT_LAYER,
    ExtractionResult,
    failed,
    truncate,
)
from app.shared.enums import DocumentExtractStatus


def extract_pdf_text(data: bytes, *, max_chars: int = 0) -> ExtractionResult:
    """PDF 바이트에서 텍스트를 뽑는다.

    입력: 파일 바이트, max_chars(0 이면 자르지 않는다).
    출력: ExtractionResult.

    - 일부 page 만 읽혔으면 partial 이고 details 에 page 수를 남긴다
    - 한 page 도 텍스트가 없으면 no_text_layer 로 실패한다 (스캔 이미지 PDF)
    - 열 수 없으면 corrupted_file 로 실패한다
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # 빈 암호로 열리는 경우가 있다. 그래도 안 되면 읽을 수 없는 파일로 본다.
            if reader.decrypt("") == 0:
                return failed(EXTRACT_ERROR_CORRUPTED)
        page_count = len(reader.pages)
    except (PyPdfError, ValueError, OSError):
        return failed(EXTRACT_ERROR_CORRUPTED)

    if page_count == 0:
        return failed(EXTRACT_ERROR_CORRUPTED)

    chunks: list[str] = []
    extracted_pages = 0
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except (PyPdfError, ValueError, KeyError):
            # page 하나가 깨져도 나머지는 살린다.
            continue
        if page_text.strip():
            chunks.append(page_text)
            extracted_pages += 1

    if extracted_pages == 0:
        return failed(EXTRACT_ERROR_NO_TEXT_LAYER)

    text, is_truncated = truncate("\n\n".join(chunks).strip(), max_chars)
    partial = is_truncated or extracted_pages < page_count
    return ExtractionResult(
        text=text,
        status=DocumentExtractStatus.PARTIAL if partial else DocumentExtractStatus.SUCCEEDED,
        is_truncated=is_truncated,
        details={"pageCount": page_count, "extractedPages": extracted_pages},
    )
