"""인증된 사용자의 포트폴리오 파일 preview.

파일만 받는 경로이므로 공고를 조회하지 않고, 사용자 소유권은 로그인 세션에서 얻는다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import current_user
from app.db.models.user import User
from app.db.session import get_db
from app.features.documents import service
from app.features.documents.schemas import DocumentPreviewResponse
from app.integrations.vision.elice import EliceVisionClient

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/preview", response_model=DocumentPreviewResponse)
async def preview(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[Literal["portfolio", "cover_letter"], Form(alias="docType")] = "portfolio",
) -> DocumentPreviewResponse:
    settings: Settings = request.app.state.settings
    user_id = user.id
    # 인증 조회 transaction을 외부 문서 처리 동안 유지하지 않는다. 저장 전 소유자를 재확인한다.
    await db.rollback()
    vision = getattr(request.app.state, "vision_client", None)
    vision_unavailable = False
    if vision is None and (
        settings.vision_base_url
        or settings.vision_api_key
        or settings.helpy_vision_document_proxy_url
    ):
        try:
            vision = EliceVisionClient(settings.require_vision())
        except ValueError:
            # 선택 공급자의 설정 오류가 native TXT/DOCX 추출까지 실패시키지 않는다.
            vision_unavailable = True
    return await service.preview_document(
        db,
        user_id,
        file,
        max_file_bytes=(
            settings.max_upload_bytes_cover_letter
            if doc_type == "cover_letter"
            else settings.max_upload_bytes_portfolio
        ),
        doc_type=doc_type,
        max_text_chars=settings.documents_max_text_chars,
        max_source_chars=settings.documents_max_source_chars,
        vision_client=vision,
        vision_pdf_layout=settings.vision_pdf_layout,
        vision_unavailable=vision_unavailable,
    )
