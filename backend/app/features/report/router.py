"""GET /interviews/{id}/report — 있으면 200, 생성을 시작했거나 진행 중이면 202.
리포트 이의제기 API·row 생성은 Sprint 2다.

docs/layer-rules.md 1절 / task-16
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.db.models.user import User
from app.db.session import get_db
from app.features.report import service
from app.features.report.schemas import GeneratingResponse, ReportResponse
from app.shared.enums import Reason

router = APIRouter(prefix="/interviews", tags=["reports"])
Database = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.get(
    "/{interview_id}/report",
    response_model=ReportResponse | GeneratingResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": GeneratingResponse}},
)
async def get_report(
    interview_id: str, request: Request, response: Response, db: Database, user: CurrentUser
) -> ReportResponse | GeneratingResponse:
    result = await service.get_report(
        db, request.app.state.redis, user_id=user.id, interview_id=_parse_id(interview_id)
    )
    if isinstance(result, GeneratingResponse):
        response.status_code = status.HTTP_202_ACCEPTED
    return result


def _parse_id(interview_id: str) -> uuid.UUID:
    """UUID 가 아닌 id 도 없는 면접이다. 계약에 400 이 없어 not_found 로 낸다."""
    try:
        return uuid.UUID(interview_id)
    except ValueError:
        raise AppError(Reason.NOT_FOUND) from None
