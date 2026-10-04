"""세션 / 턴 읽기 쿼리.

면접 생성 검사 기준은 spec/backend/features/interview.md "생성 검사 해석"을 따른다.

docs/layer-rules.md 1절 / task-13
"""

import uuid
from collections.abc import Collection

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    InterviewSession,
    RepoAnalysis,
    Repository,
)
from app.db.models.interview import ACTIVE_INTERVIEW_STATUSES

# 면접을 만들 수 있는 run 상태. partial 도 성공한 repo 는 쓸 수 있다.
_INTERVIEWABLE_RUN_STATUSES = ("succeeded", "partial")


async def get_current_run(
    db: AsyncSession, *, user_id: uuid.UUID, run_id: uuid.UUID
) -> AnalysisJob | None:
    """면접을 만들 수 있는 run 을 찾는다.

    입력: 요청 사용자 id, runId. 출력: 본인 소유 · analysis_run · succeeded/partial ·
    공고 있음을 모두 만족하면 AnalysisJob, 아니면 None (service 가 run_expired 로 변환).
    """
    run: AnalysisJob | None = await db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.id == run_id,
            AnalysisJob.user_id == user_id,
            AnalysisJob.job_type == "analysis_run",
            AnalysisJob.status.in_(_INTERVIEWABLE_RUN_STATUSES),
            AnalysisJob.job_posting_id.is_not(None),
        )
    )
    return run


async def select_selectable_repository_ids(
    db: AsyncSession, *, run_id: uuid.UUID, repository_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    """repository_ids 중 이 run 에서 면접 대상으로 고를 수 있는 id 만 돌려준다.

    입력: runId, 요청 repo id 목록. 출력: 선택 가능한 id 집합.
    조건: run 후보 eligible · public · accessible · L1 succeeded 행 존재.
    """
    # ponytail: L1 은 head_sha 와 무관하게 성공 행이 하나라도 있으면 통과. 최신 sha 기준이
    # 필요해지면 RepoAnalysis.head_sha == Repository.head_sha 조건을 추가한다.
    l1_succeeded = exists().where(
        RepoAnalysis.repository_id == Repository.id,
        RepoAnalysis.analysis_level == "l1",
        RepoAnalysis.status == "succeeded",
    )
    rows = await db.scalars(
        select(Repository.id)
        .join(AnalysisRepoCandidate, AnalysisRepoCandidate.repository_id == Repository.id)
        .where(
            AnalysisRepoCandidate.analysis_job_id == run_id,
            AnalysisRepoCandidate.filter_status == "eligible",
            Repository.id.in_(repository_ids),
            Repository.is_private.is_(False),
            Repository.is_accessible.is_(True),
            l1_succeeded,
        )
    )
    return set(rows)


async def has_active_interview(db: AsyncSession, *, run_id: uuid.UUID) -> bool:
    """run 에 preparing / in_progress 면접이 있는지. 입력: runId. 출력: bool."""
    found = await db.scalar(
        select(
            exists().where(
                InterviewSession.analysis_job_id == run_id,
                InterviewSession.status.in_(ACTIVE_INTERVIEW_STATUSES),
            )
        )
    )
    return bool(found)
