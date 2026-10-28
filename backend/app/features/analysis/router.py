"""분석 API. 소유권·실행 정책은 service에서 처리한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.deps import current_user, get_db
from app.db.models.user import User
from app.features.analysis import service
from app.features.analysis.run_queries import owned_run
from app.features.analysis.run_schemas import (
    AnalysisRunResponse,
    AnalysisRunResultResponse,
    AnalyzingResponse,
    CandidatesResponse,
    CreateAnalysisRunRequest,
    CreateAnalysisRunResponse,
)
from app.features.analysis.stream import analysis_events
from app.realtime.sse import run_progress_response

router = APIRouter(prefix="/analysis-runs", tags=["analysis"])
Database = Annotated[AsyncSession, Depends(get_db)]
Member = Annotated[User, Depends(current_user)]


@router.post("", status_code=202, response_model=CreateAnalysisRunResponse)
async def create(
    payload: CreateAnalysisRunRequest,
    request: Request,
    response: Response,
    db: Database,
    user: Member,
) -> CreateAnalysisRunResponse:
    identity = await service.create_run(db, user.id, payload, request.app.state.redis)
    response.headers["Location"] = (
        f"{request.app.state.settings.api_prefix}/analysis-runs/{identity}"
    )
    return CreateAnalysisRunResponse(run_id=identity)


@router.get("/{run_id}", response_model=AnalysisRunResponse)
async def status(run_id: UUID, request: Request, db: Database, user: Member) -> AnalysisRunResponse:
    return await service.get_status(db, user.id, run_id, request.app.state.settings)


@router.get("/{run_id}/result", response_model=AnalysisRunResultResponse)
async def result(
    run_id: UUID, request: Request, db: Database, user: Member
) -> AnalysisRunResultResponse:
    return await service.get_result(db, user.id, run_id, request.app.state.settings)


@router.get("/{run_id}/candidates", response_model=CandidatesResponse | AnalyzingResponse)
async def candidates(
    run_id: UUID,
    page: Annotated[int, Query(ge=1)],
    request: Request,
    response: Response,
    db: Database,
    user: Member,
) -> CandidatesResponse | AnalyzingResponse:
    result = await service.get_candidates(
        db, user.id, run_id, page, request.app.state.settings, request.app.state.redis
    )
    if isinstance(result, AnalyzingResponse):
        response.status_code = 202
    return result


@router.get("/{run_id}/events")
async def events(run_id: UUID, request: Request, db: Database, user: Member) -> EventSourceResponse:
    await owned_run(db, run_id, user.id, request.app.state.settings.analysis_run_ttl_seconds)
    await db.commit()
    return run_progress_response(
        analysis_events(request.app.state.session_factory, request.app.state.redis, run_id, user.id)
    )
