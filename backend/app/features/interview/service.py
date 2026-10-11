"""세션 생성 / 동시 면접 제한 / sessionId 발급.
★ job_posting_id 가 NOT NULL 이다 (공고 필수).
★ status = preparing / preparing_failed / in_progress / completed / abandoned. paused 없음.
★ answer_mode = 'text' 고정 (CHECK). 2차에 voice 완화.
★ 명시적 이탈·레포 재선택만 status='abandoned' + abandoned_at_turn으로 처리한다.
  WS 끊김은 재연결 대상이며 미답변 턴은 asked로 남는다. 자동 timeout 이탈 판정은 없다.
  실제 상태 저장·연결은 구현 대기다.

생성 검사 기준은 spec/backend/features/interview.md "생성 검사 해석".

확정본 §5 interview_sessions / task-13
"""

import json
import secrets
import uuid

from arq.connections import ArqRedis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import InterviewSession, SessionRepository
from app.features.interview import queries
from app.shared.enums import Reason

# rt:{sessionId} TTL (docs/pipeline.md 4.4, docs/redis-keys.md).
REALTIME_SESSION_TTL_SECONDS = 2 * 60 * 60
_ACTIVE_PER_RUN_INDEX = "uq_interview_sessions_active_per_run"


async def create_interview(
    db: AsyncSession,
    redis: ArqRedis,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    repository_ids: list[uuid.UUID],
) -> tuple[uuid.UUID, str]:
    """면접을 만들고 interview_prep 을 enqueue 한다.

    입력: 요청 사용자 id, runId, 선택 repo id 목록(요청 순서 = display_order).
    출력: (interviewId, sessionId). 검사 실패는 AppError.
    """
    if not repository_ids:
        raise AppError(Reason.NO_REPOSITORY_SELECTED)
    if len(repository_ids) > get_settings().max_selected_repos:
        raise AppError(Reason.TOO_MANY_REPOSITORIES)
    # 중복 id 는 session_repositories UNIQUE 에 걸려 500 이 되므로 선택 불가로 본다.
    if len(set(repository_ids)) != len(repository_ids):
        raise AppError(Reason.INVALID_REPOSITORY)

    run = await queries.get_current_run(db, user_id=user_id, run_id=run_id)
    if run is None or run.job_posting_id is None:
        raise AppError(Reason.RUN_EXPIRED)
    selectable = await queries.select_selectable_repository_ids(
        db, run_id=run_id, repository_ids=repository_ids
    )
    if selectable != set(repository_ids):
        raise AppError(Reason.INVALID_REPOSITORY)
    if await queries.has_active_interview(db, run_id=run_id):
        raise AppError(Reason.SESSION_LIMIT_EXCEEDED)

    interview = InterviewSession(
        user_id=user_id, analysis_job_id=run.id, job_posting_id=run.job_posting_id
    )
    db.add(interview)
    try:
        await db.flush()
    except IntegrityError as exc:
        # 사전 조회와 INSERT 사이에 동시 요청이 먼저 들어온 경우. 다른 제약 위반은 그대로 올린다.
        await db.rollback()
        if _ACTIVE_PER_RUN_INDEX in str(exc.orig):
            raise AppError(Reason.SESSION_LIMIT_EXCEEDED) from None
        raise
    db.add_all(
        SessionRepository(interview_session_id=interview.id, repository_id=repo_id, display_order=i)
        for i, repo_id in enumerate(repository_ids)
    )
    # worker 가 행을 볼 수 있도록 enqueue 전에 commit 한다.
    await db.commit()

    session_id = secrets.token_urlsafe(32)
    try:
        await redis.set(
            f"rt:{session_id}",
            json.dumps({"interviewId": str(interview.id), "userId": str(user_id)}),
            ex=REALTIME_SESSION_TTL_SECONDS,
        )
        await redis.enqueue_job("interview_prep", str(interview.id))
    except RedisError:
        # 준비 job 없는 preparing 행이 남으면 같은 run 의 새 면접이 영구히 막히므로 되돌린다.
        await db.delete(interview)
        await db.commit()
        raise AppError(Reason.INTERNAL_ERROR) from None
    return interview.id, session_id
