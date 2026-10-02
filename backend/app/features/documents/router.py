"""인증된 사용자의 포트폴리오 파일 preview.

파일만 받는 경로이므로 공고를 조회하지 않고, 사용자 소유권은 로그인 세션에서 얻는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import current_user
from app.db.models.user import User
from app.db.session import get_db
from app.features.documents import service
from app.features.documents.schemas import DocumentPreviewResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/preview", response_model=DocumentPreviewResponse)
async def preview(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
) -> DocumentPreviewResponse:
    settings: Settings = request.app.state.settings
    return await service.preview_document(
        db,
        user,
        file,
        max_file_bytes=settings.max_upload_bytes_portfolio,
        max_text_chars=settings.documents_max_text_chars,
    )
