"""/interviews REST. 구현 예정: /{id}/retry.
준비 실패 재시도는 REST POST /interviews/{id}/prepare/retry이며 WS 메시지가 아니다.
main.py 등록은 interview_prep 워커 연결(AI task-06) 때 한다.
그 전에 열면 면접이 preparing 에 머문다.

docs/layer-rules.md 1절 / task-13
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.db.models.user import User
from app.db.session import get_db
from app.features.interview import service
from app.features.interview.schemas import (
    CreateInterviewRequest,
    CreateInterviewResponse,
    InterviewDetailResponse,
)
from app.shared.enums import Reason

router = APIRouter(prefix="/interviews", tags=["interviews"])
Database = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateInterviewResponse)
async def create_interview(
    body: CreateInterviewRequest, request: Request, db: Database, user: CurrentUser
) -> CreateInterviewResponse:
    interview_id, session_id = await service.create_interview(
        db,
        request.app.state.redis,
        user_id=user.id,
        run_id=body.run_id,
        repository_ids=body.repository_ids,
    )
    return CreateInterviewResponse(session_id=session_id, interview_id=interview_id)


@router.get("/{interview_id}", response_model=InterviewDetailResponse)
async def get_interview(
    interview_id: str, request: Request, db: Database, user: CurrentUser
) -> InterviewDetailResponse:
    return await service.get_interview(
        db,
        request.app.state.redis,
        user_id=user.id,
        interview_id=_parse_id(interview_id, Reason.NOT_FOUND),
    )


@router.post("/{interview_id}/prepare/retry", status_code=status.HTTP_204_NO_CONTENT)
async def retry_prepare(
    interview_id: str, request: Request, db: Database, user: CurrentUser
) -> None:
    await service.retry_prepare(
        db,
        request.app.state.redis,
        user_id=user.id,
        interview_id=_parse_id(interview_id, Reason.SESSION_EXPIRED),
    )


def _parse_id(interview_id: str, missing: Reason) -> uuid.UUID:
    """UUID 가 아닌 id 도 없는 면접이다. 계약에 400 이 없어 그 route 의 '없음' reason 으로 낸다."""
    try:
        return uuid.UUID(interview_id)
    except ValueError:
        raise AppError(missing) from None
