"""문서 preview 검증과 추출 결과 저장 트랜잭션."""

from pathlib import PurePath
from typing import Literal
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError
from app.core.security import require_active_user
from app.db.models.document import UserDocument
from app.db.models.user import User
from app.features.documents import queries
from app.features.documents.processing import process_document
from app.features.documents.schemas import DocumentPreviewResponse
from app.features.documents.source_snapshot import snapshot_document
from app.features.documents.vision_processing import mark_vision_unavailable, supplement_with_vision
from app.integrations.extract.base import DocumentFormat, failed
from app.integrations.vision.elice import EliceVisionClient
from app.shared.enums import Reason

_MIME_TYPES = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentFormat.TXT: "text/plain",
    DocumentFormat.MD: "text/markdown",
}
_VISION_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


async def preview_document(
    db: AsyncSession,
    user: User | UUID,
    upload: UploadFile,
    *,
    max_file_bytes: int,
    max_text_chars: int,
    max_source_chars: int = 262144,
    doc_type: Literal["portfolio", "cover_letter"] = "portfolio",
    vision_client: EliceVisionClient | None = None,
    vision_pdf_layout: bool = False,
    vision_unavailable: bool = False,
) -> DocumentPreviewResponse:
    user_id = user if isinstance(user, UUID) else user.id
    try:
        # 클라이언트 OS와 무관하게 경로를 제외한 표시용 파일명만 저장한다.
        filename = (upload.filename or "").replace("\x00", "").replace("\\", "/").rsplit("/", 1)[-1]
        suffix = PurePath(filename).suffix.lower().removeprefix(".")
        # MIME은 클라이언트 입력이므로 미지원 확장자의 우회 근거로 사용하지 않는다.
        if suffix not in DocumentFormat and (
            (vision_client is None and not vision_unavailable) or suffix not in _VISION_MIME_TYPES
        ):
            raise AppError(Reason.UNSUPPORTED_DOCUMENT_TYPE)
        document_format = DocumentFormat(suffix) if suffix in DocumentFormat else None
        # multipart 메타데이터가 아닌 실제 파일 바이트를 검사하며 초과분은 한 바이트만 읽는다.
        data = await upload.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise AppError(Reason.DOCUMENT_TOO_LARGE)
        # 동기 파싱이 이벤트 루프를 막지 않게 위임하며 DB 세션은 작업 스레드에 넘기지 않는다.
        if document_format is not None:
            result, urls = await run_in_threadpool(
                process_document, data, document_format, max_chars=max_text_chars
            )
            mime_type = _MIME_TYPES[document_format]
        else:
            result, urls = failed("no_text_layer"), []
            mime_type = _VISION_MIME_TYPES[suffix]
        needs_vision = (
            document_format is None
            # 완전한 텍스트 PDF의 레이아웃 보완은 명시적으로 선택한 경우에만 전송한다.
            or (document_format is DocumentFormat.PDF and vision_pdf_layout)
            or result.error_code == "no_text_layer"
            or (result.details.get("pageCount", 0) > result.details.get("extractedPages", 0))
        )
        if vision_client is not None and needs_vision:
            result, vision_urls = await supplement_with_vision(
                data,
                mime_type,
                filename,
                result,
                vision_client,
                max_preview_chars=max_text_chars,
            )
            urls = list(dict.fromkeys(urls + vision_urls))
        elif needs_vision and vision_unavailable:
            result = mark_vision_unavailable(result, "vision_configuration_invalid")
    finally:
        await upload.close()

    owner = await db.get(User, user_id, populate_existing=True)
    if owner is None:
        raise AppError(Reason.UNAUTHENTICATED)
    require_active_user(owner.status)
    document = UserDocument(
        user_id=user_id,
        doc_type=doc_type,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        extracted_text=result.text or None,
        extracted_github_urls=urls,
        extract_status=result.status.value,
        extract_error_code=result.error_code,
        is_truncated=result.is_truncated,
        source_snapshot=snapshot_document(
            data,
            result,
            max_chars=max_source_chars,
            method="elice_vision" if result.source_metadata else "native_text",
        ),
        claims_status="pending"
        if result.succeeded and (result.source_text or result.text).strip()
        else "not_available",
    )
    await queries.insert_document(db, document)
    # failed도 조회 가능한 문서 ID가 필요하므로 저장한다. DB 오류는 공통 500 처리로 보낸다.
    await db.commit()
    return DocumentPreviewResponse(document_id=document.id, extract_status=result.status)
