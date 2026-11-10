"""GET /interviews/{id}/report — 있으면 200, 생성을 시작했거나 진행 중이면 202.
이의 접수는 점수를 변경하지 않으며 실패한 생성만 소유자가 명시 재시도할 수 있다.

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
from app.features.report import generation, queries, reviews, service
from app.features.report.schemas import (
    FeedbackDisagreementRequest,
    GeneratingResponse,
    ReportResponse,
)
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


@router.post("/{interview_id}/feedback-disagreements", status_code=204)
async def submit_feedback_disagreement(
    interview_id: str, body: FeedbackDisagreementRequest, db: Database, user: CurrentUser
) -> Response:
    await reviews.submit(db, user_id=user.id, interview_id=_parse_id(interview_id), body=body)
    return Response(status_code=204)


@router.post("/{interview_id}/report/retry", status_code=202, response_model=GeneratingResponse)
async def retry_report(
    interview_id: str, request: Request, db: Database, user: CurrentUser
) -> GeneratingResponse:
    identity = _parse_id(interview_id)
    if not service.enough_answers(await queries.list_answered_turns(db, interview_id=identity)):
        # 소유권 여부를 먼저 확인해 타 사용자 상태를 추측할 수 없게 한다.
        await generation.locked_interview(db, identity, user.id)
        raise AppError(Reason.REPORT_UNAVAILABLE)
    await generation.enqueue(
        db, request.app.state.redis, interview_id=identity, user_id=user.id, mode="retry"
    )
    return GeneratingResponse(retry_after=service.RETRY_AFTER_SECONDS)


def _parse_id(interview_id: str) -> uuid.UUID:
    """UUID 가 아닌 id 도 없는 면접이다. 계약에 400 이 없어 not_found 로 낸다."""
    try:
        return uuid.UUID(interview_id)
    except ValueError:
        raise AppError(Reason.NOT_FOUND) from None
