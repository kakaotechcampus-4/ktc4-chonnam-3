"""/interviews REST. 구현 예정: /{id}/retry, /{id}/prepare/retry.
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
    # 계약은 401/404 만 둔다. UUID 가 아닌 id 도 없는 면접이므로 400 대신 404.
    try:
        parsed = uuid.UUID(interview_id)
    except ValueError:
        raise AppError(Reason.NOT_FOUND) from None
    return await service.get_interview(
        db, request.app.state.redis, user_id=user.id, interview_id=parsed
    )
