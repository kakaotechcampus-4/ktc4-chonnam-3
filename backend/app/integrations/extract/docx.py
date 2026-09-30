"""DOCX 텍스트 추출 (자소서 / 포트폴리오).

docs/layer-rules.md 1절 / task-09

포트폴리오는 표로 프로젝트를 정리하는 경우가 흔해 표 안의 글자도 함께 읽는다.
"""

import io
from zipfile import BadZipFile

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from lxml.etree import XMLSyntaxError

from app.integrations.extract.base import (
    EXTRACT_ERROR_CORRUPTED,
    EXTRACT_ERROR_EMPTY,
    ExtractionResult,
    failed,
    truncate,
)
from app.shared.enums import DocumentExtractStatus

# 열린 뒤 문단·표를 읽다가 손상된 XML 값을 만났을 때 나오는 예외들.
# gridSpan="bad" 는 ValueError, w:body 가 없으면 AttributeError 다.
_READ_ERRORS = (ValueError, KeyError, AttributeError, TypeError, IndexError, XMLSyntaxError)


def _table_lines(table: Table) -> list[str]:
    """표 한 개를 줄 목록으로 편다. 입력: Table. 출력: 빈 줄을 뺀 줄 목록."""
    lines: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        joined = " | ".join(cell for cell in cells if cell)
        if joined:
            lines.append(joined)
    return lines


def extract_docx_text(data: bytes, *, max_chars: int = 0) -> ExtractionResult:
    """DOCX 바이트에서 텍스트를 뽑는다.

    입력: 파일 바이트, max_chars(0 이면 자르지 않는다).
    출력: ExtractionResult.

    - 열 수 없으면 corrupted_file
    - 문단과 표에 글자가 하나도 없으면 empty_document
    - 열린 뒤 일부 표가 깨졌으면 읽은 만큼 partial, 읽은 것이 없으면 corrupted_file
    - 길이 상한으로 잘렸으면 partial
    """
    try:
        document = docx.Document(io.BytesIO(data))
    # BadZipFile 은 OSError 계열이 아니다 — docx 는 zip 이라 깨진 파일이 여기로 온다.
    # XMLSyntaxError 는 SyntaxError 계열이라 위 예외들과 공통 조상이 없다 — zip은 멀쩡한데
    # 내부 document.xml 이 깨진 경우(예: 손상된 저장) 여기로 온다.
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError, OSError, XMLSyntaxError):
        return failed(EXTRACT_ERROR_CORRUPTED)

    # 파일을 연 뒤에도 손상된 구조(잘못된 gridSpan, w:body 없음 등)는 순회 중에 터진다.
    # 예외 대신 결과 객체로 돌려준다 — 읽은 내용이 있으면 partial, 없으면 corrupted_file.
    lines: list[str] = []
    table_count = 0
    broken = False
    try:
        paragraphs = document.paragraphs
        lines = [paragraph.text.strip() for paragraph in paragraphs if paragraph.text.strip()]
        tables = document.tables
    except _READ_ERRORS:
        return failed(EXTRACT_ERROR_CORRUPTED)
    for table in tables:
        table_count += 1
        try:
            lines.extend(_table_lines(table))
        except _READ_ERRORS:
            # 표 하나가 깨져도 나머지는 살린다.
            broken = True

    if not lines:
        return failed(EXTRACT_ERROR_CORRUPTED if broken else EXTRACT_ERROR_EMPTY)

    text, is_truncated = truncate("\n".join(lines).strip(), max_chars)
    return ExtractionResult(
        text=text,
        status=(
            DocumentExtractStatus.PARTIAL
            if is_truncated or broken
            else DocumentExtractStatus.SUCCEEDED
        ),
        is_truncated=is_truncated,
        details={"paragraphCount": len(paragraphs), "tableCount": table_count},
    )
