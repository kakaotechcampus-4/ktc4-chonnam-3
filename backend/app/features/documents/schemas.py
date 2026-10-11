"""문서 preview의 공통 API 응답."""

from uuid import UUID

from app.shared.enums import DocumentExtractStatus
from app.shared.schema import CamelResponse


class DocumentPreviewResponse(CamelResponse):
    document_id: UUID
    extract_status: DocumentExtractStatus
