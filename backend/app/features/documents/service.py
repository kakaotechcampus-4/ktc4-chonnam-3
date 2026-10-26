"""문서 preview 검증과 추출 결과 저장 트랜잭션."""

from pathlib import PurePath

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError
from app.db.models.document import UserDocument
from app.db.models.user import User
from app.features.documents import queries
from app.features.documents.processing import process_document
from app.features.documents.schemas import DocumentPreviewResponse
from app.integrations.extract.base import DocumentFormat
from app.shared.enums import Reason

_MIME_TYPES = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentFormat.TXT: "text/plain",
    DocumentFormat.MD: "text/markdown",
}


async def preview_document(
    db: AsyncSession,
    user: User,
    upload: UploadFile,
    *,
    max_file_bytes: int,
    max_text_chars: int,
) -> DocumentPreviewResponse:
    try:
        # 클라이언트 OS와 무관하게 경로를 제외한 표시용 파일명만 저장한다.
        filename = (upload.filename or "").replace("\x00", "").replace("\\", "/").rsplit("/", 1)[-1]
        suffix = PurePath(filename).suffix.lower().removeprefix(".")
        # MIME은 클라이언트 입력이므로 미지원 확장자의 우회 근거로 사용하지 않는다.
        if suffix not in DocumentFormat:
            raise AppError(Reason.UNSUPPORTED_DOCUMENT_TYPE)
        document_format = DocumentFormat(suffix)
        # multipart 메타데이터가 아닌 실제 파일 바이트를 검사하며 초과분은 한 바이트만 읽는다.
        data = await upload.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise AppError(Reason.DOCUMENT_TOO_LARGE)
        # 동기 파싱이 이벤트 루프를 막지 않게 위임하며 DB 세션은 작업 스레드에 넘기지 않는다.
        result, urls = await run_in_threadpool(
            process_document, data, document_format, max_chars=max_text_chars
        )
    finally:
        await upload.close()

    document = UserDocument(
        user_id=user.id,
        doc_type="portfolio",
        filename=filename,
        mime_type=_MIME_TYPES[document_format],
        size_bytes=len(data),
        extracted_text=result.text or None,
        extracted_github_urls=urls,
        extract_status=result.status.value,
        extract_error_code=result.error_code,
        is_truncated=result.is_truncated,
    )
    await queries.insert_document(db, document)
    # failed도 조회 가능한 문서 ID가 필요하므로 저장한다. DB 오류는 공통 500 처리로 보낸다.
    await db.commit()
    return DocumentPreviewResponse(document_id=document.id, extract_status=result.status)
