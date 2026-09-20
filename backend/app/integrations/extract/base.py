"""문서 추출 공통 타입과 형식 판정.

spec/backend/features/documents.md / task-09

integrations 는 DB 를 모른다. 여기서는 status 와 error_code 만 판단하고
user_documents 행을 쓰는 것은 service 가 한다.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.shared.enums import DocumentExtractStatus


class DocumentFormat(StrEnum):
    """Sprint 1 이 받는 4개 형식. hwp·이미지·ppt/pptx 는 미지원이다."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


# 업로드 시 브라우저가 붙이는 MIME 과 확장자 양쪽으로 판정한다.
# MIME 은 신뢰할 수 없어 확장자를 우선한다 (빈 값이나 octet-stream 이 흔하다).
_FORMAT_BY_SUFFIX: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".txt": DocumentFormat.TXT,
    ".md": DocumentFormat.MD,
    ".markdown": DocumentFormat.MD,
}

# 추출 실패 사유. user_documents.extract_error_code 에 그대로 들어간다.
EXTRACT_ERROR_UNSUPPORTED = "unsupported_document_type"
EXTRACT_ERROR_NO_TEXT_LAYER = "no_text_layer"
EXTRACT_ERROR_CORRUPTED = "corrupted_file"
EXTRACT_ERROR_EMPTY = "empty_document"


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """추출 결과 한 건.

    status 는 openapi DocumentExtractStatus 와 같은 값이다.
    - succeeded: 텍스트를 모두 얻었다
    - partial: 일부 page/문단만 읽었거나 길이 초과로 잘랐다
    - failed: 텍스트를 하나도 얻지 못했다
    """

    text: str
    status: DocumentExtractStatus
    is_truncated: bool = False
    error_code: str | None = None
    # 진단용. 몇 page 중 몇 page 를 읽었는지 같은 값이 들어간다.
    details: dict[str, int] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status is not DocumentExtractStatus.FAILED


def detect_format(filename: str, mime_type: str | None = None) -> DocumentFormat | None:
    """파일 이름과 MIME 으로 형식을 고른다.

    입력: filename(확장자 포함), mime_type(선택).
    출력: DocumentFormat, 지원하지 않으면 None.
    확장자를 우선한다 — 업로드 MIME 은 비어 있거나 octet-stream 인 경우가 흔하다.
    """
    lowered = filename.lower()
    for suffix, document_format in _FORMAT_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            return document_format

    if mime_type is None:
        return None
    normalized = mime_type.split(";")[0].strip().lower()
    if normalized == "application/pdf":
        return DocumentFormat.PDF
    if normalized == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return DocumentFormat.DOCX
    if normalized == "text/markdown":
        return DocumentFormat.MD
    if normalized == "text/plain":
        return DocumentFormat.TXT
    return None


def failed(error_code: str) -> ExtractionResult:
    """실패 결과를 만든다. 입력: error_code. 출력: ExtractionResult."""
    return ExtractionResult(
        text="",
        status=DocumentExtractStatus.FAILED,
        error_code=error_code,
    )


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    """길이 상한으로 자른다.

    입력: 원문, 최대 글자 수. 출력: (자른 텍스트, 잘렸는지 여부).
    0 이하면 자르지 않는다.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
