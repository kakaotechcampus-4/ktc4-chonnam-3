"""/analysis-runs (POST), /{runId}, /{runId}/result, /{runId}/candidates.

/{runId}/events(SSE) 는 task-12 범위다. 이번 작업 범위는 폴링 API 까지다.

docs/layer-rules.md 1절 / task-11
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.deps import ArqPool, CurrentUser, DbSession
from app.features.analysis import service
from app.features.analysis.schemas import (
    AnalysisRunResponse,
    AnalysisRunResultResponse,
    AnalyzingResponse,
    CandidatePageResponse,
    CreateAnalysisRunRequest,
    CreateAnalysisRunResponse,
)

router = APIRouter(prefix="/analysis-runs", tags=["analysis"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateAnalysisRunResponse,
)
async def create_analysis_run(
    payload: CreateAnalysisRunRequest,
    db: DbSession,
    arq: ArqPool,
    user: CurrentUser,
    response: Response,
) -> CreateAnalysisRunResponse:
    """공고 URL(필수) + 문서 id(선택)로 분석 run 을 시작한다."""
    result = await service.create_run(
        db,
        arq,
        user,
        posting_url=payload.posting_url,
        document_id=payload.document_id,
    )
    response.headers["Location"] = f"/analysis-runs/{result.run_id}"
    return result


@router.get("/{run_id}", response_model=AnalysisRunResponse)
async def get_analysis_run(
    run_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> AnalysisRunResponse:
    """진행률 폴링. 분석 실패도 200 + failureReason 으로 내려간다."""
    return await service.get_run_status(db, user, run_id)


@router.get("/{run_id}/result", response_model=AnalysisRunResultResponse)
async def get_analysis_run_result(
    run_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> AnalysisRunResultResponse:
    """첫 batch 레포 목록. partial run 도 조회 가능하다."""
    return await service.get_run_result(db, user, run_id)


@router.get(
    "/{run_id}/candidates",
    response_model=CandidatePageResponse | AnalyzingResponse,
)
async def get_analysis_run_candidates(
    run_id: uuid.UUID,
    db: DbSession,
    arq: ArqPool,
    user: CurrentUser,
    response: Response,
    page: Annotated[int, Query(ge=1)],
) -> CandidatePageResponse | AnalyzingResponse:
    """'더 보기'. 완료 page 는 200, 미분석 page 는 enqueue 후 202 analyzing."""
    result = await service.get_candidate_page(db, arq, user, run_id, page)
    if isinstance(result, AnalyzingResponse):
        response.status_code = status.HTTP_202_ACCEPTED
    return result
