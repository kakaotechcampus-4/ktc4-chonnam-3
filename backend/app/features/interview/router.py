"""/interviews REST. 구현 예정: /{id}, /{id}/retry, /{id}/prepare/retry.
준비 실패 재시도는 REST POST /interviews/{id}/prepare/retry이며 WS 메시지가 아니다.
main.py 등록은 interview_prep 워커 연결(AI task-06) 때 한다.
그 전에 열면 면접이 preparing 에 머문다.

docs/layer-rules.md 1절 / task-13
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db.models.user import User
from app.db.session import get_db
from app.features.interview import service
from app.features.interview.schemas import CreateInterviewRequest, CreateInterviewResponse

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
