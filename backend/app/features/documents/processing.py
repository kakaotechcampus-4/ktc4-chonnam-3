"""파일 추출과 URL 보존, LLM 없는 길이 축약. 동기 작업은 threadpool에서 호출한다."""

import re
from dataclasses import replace
from itertools import chain

from app.integrations.extract.base import (
    EXTRACT_ERROR_EMPTY,
    DocumentFormat,
    ExtractionResult,
    failed,
)
from app.integrations.extract.docx import extract_docx_text
from app.integrations.extract.github_urls import extract_github_full_names
from app.integrations.extract.pdf import extract_pdf_text
from app.integrations.extract.plain import extract_plain_text
from app.shared.enums import DocumentExtractStatus

_HEADING = re.compile(r"^\s*(?:#{1,6}\s+\S|(?:project|프로젝트)(?:\s|:|$))", re.IGNORECASE)


def _bounded_text(text: str, max_chars: int) -> str:
    lines = text.splitlines()
    url_lines = [index for index, line in enumerate(lines) if "github.com/" in line.lower()]
    headings = [index for index, line in enumerate(lines) if _HEADING.match(line)]
    context = (neighbor for index in url_lines for neighbor in (index - 1, index + 1))
    sections = (neighbor for index in headings for neighbor in (index, index + 1))
    selected: dict[int, str] = {}
    remaining = max_chars
    # ponytail: 줄 단위 규칙 축약. 문서 레이아웃 의미 분석이 필요해질 때만 확장한다.
    # URL 본문, 주변 줄, 프로젝트 헤딩 순으로 고른 뒤 원문 순서로 저장한다.
    for index in chain(url_lines, context, sections, range(len(lines))):
        if index in selected or not 0 <= index < len(lines):
            continue
        line = lines[index].strip()
        if not line:
            continue
        available = remaining - bool(selected)
        if available <= 0:
            break
        if len(line) > available and "github.com/" in line.lower():
            # 긴 한 줄의 끝에 있는 링크도 문서 앞부분만 자르는 과정에서 사라지지 않게 한다.
            position = line.lower().index("github.com/")
            line = line[max(0, position - min(40, available // 4)) :]
        selected[index] = line[:available]
        remaining = available - len(selected[index])
    return "\n".join(selected[index] for index in sorted(selected))


def process_document(
    data: bytes, document_format: DocumentFormat, *, max_chars: int
) -> tuple[ExtractionResult, list[str]]:
    if max_chars <= 0:
        raise ValueError("Document text limit must be positive")
    extractor = {
        DocumentFormat.PDF: extract_pdf_text,
        DocumentFormat.DOCX: extract_docx_text,
        DocumentFormat.TXT: extract_plain_text,
        DocumentFormat.MD: extract_plain_text,
    }[document_format]
    result = extractor(data)
    if result.status is DocumentExtractStatus.FAILED:
        return result, []

    # PostgreSQL TEXT는 NUL을 받지 않는다. 손실은 partial로 표시하고 나머지는 보존한다.
    text = result.text.replace("\x00", "").strip()
    if not text:
        return failed(EXTRACT_ERROR_EMPTY), []
    links = "\n".join(result.hyperlinks).replace("\x00", "")
    # 문서 끝 URL과 PDF/DOCX의 숨은 링크 대상을 축약 전에 별도로 확보한다.
    urls = extract_github_full_names(text + "\n" + links)
    is_truncated = len(text) > max_chars
    partial = (
        result.status is DocumentExtractStatus.PARTIAL
        or "\x00" in result.text
        or any("\x00" in link for link in result.hyperlinks)
        or is_truncated
    )
    return replace(
        result,
        text=_bounded_text(text, max_chars) if is_truncated else text,
        status=DocumentExtractStatus.PARTIAL if partial else DocumentExtractStatus.SUCCEEDED,
        is_truncated=result.is_truncated or is_truncated,
    ), urls
