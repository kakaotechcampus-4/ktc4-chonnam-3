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
from datetime import UTC, datetime

from arq.connections import ArqRedis
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewSession, SessionRepository
from app.features.interview import queries
from app.features.interview.schemas import (
    InterviewDetailResponse,
    InterviewLastError,
    InterviewTurn,
)
from app.shared.enums import Reason

# rt:{sessionId} TTL (docs/pipeline.md 4.4, docs/redis-keys.md).
REALTIME_SESSION_TTL_SECONDS = 2 * 60 * 60
_ACTIVE_PER_RUN_INDEX = "uq_interview_sessions_active_per_run"
logger = get_logger(__name__)


async def create_interview(
    db: AsyncSession,
    redis: ArqRedis,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    repository_ids: list[uuid.UUID],
    retry_of: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    """면접을 만들고 interview_prep 을 enqueue 한다.

    입력: 요청 사용자 id, runId, 선택 repo id 목록(요청 순서 = display_order),
    재도전이면 원본 interviewId. 출력: (interviewId, sessionId). 검사 실패는 AppError.
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
        user_id=user_id,
        analysis_job_id=run.id,
        job_posting_id=run.job_posting_id,
        retry_of_interview_id=retry_of,
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

    interview_id = interview.id
    try:
        session_id = await _issue_session_id(redis, interview_id=interview_id, user_id=user_id)
        await redis.enqueue_job("interview_prep", str(interview_id))
    except RedisError:
        # 준비 job 없는 preparing 행이 남으면 같은 run 의 새 면접이 영구히 막히므로 되돌린다.
        try:
            await db.delete(interview)
            await db.commit()
        except SQLAlchemyError:
            # ponytail: 되돌리기 실패 행은 id 로그만 남긴다. 자동 정리는 준비 job reaper 에서.
            logger.error("interview_create_rollback_failed", interview_id=str(interview_id))
        raise AppError(Reason.INTERNAL_ERROR) from None
    return interview_id, session_id


async def get_interview(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> InterviewDetailResponse:
    """준비·진행 화면이 새로고침 후 복구할 상태. 없거나 남의 면접이면 not_found."""
    row = await queries.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    if row is None:
        raise AppError(Reason.NOT_FOUND)
    interview, posting = row
    try:
        session_id = await _current_session_id(redis, interview_id=interview.id, user_id=user_id)
    except RedisError:
        raise AppError(Reason.INTERNAL_ERROR) from None
    turns = await queries.list_turns(db, interview_id=interview.id)
    return InterviewDetailResponse(
        id=interview.id,
        session_id=session_id,
        run_id=interview.analysis_job_id,
        status=interview.status,
        answer_mode=interview.answer_mode,
        position=posting.position or "",
        company_name=posting.company_name,
        repository_names=await queries.list_repository_names(db, interview_id=interview.id),
        current_turn=interview.current_turn,
        total_turns=interview.total_turns,
        remaining_seconds=_remaining_seconds(interview),
        turns=[
            InterviewTurn(
                turn=t.turn_no, persona=t.persona, question=t.question_text, answer=t.answer_text
            )
            for t in turns
        ],
        # openapi: preparing_failed 일 때만 내려준다.
        last_error=_last_error(interview) if interview.status == "preparing_failed" else None,
    )


def _last_error(interview: InterviewSession) -> InterviewLastError | None:
    """저장된 JSONB 모양이 어긋나도 GET 전체를 500으로 만들지 않고 lastError 만 비운다."""
    if not interview.last_error:
        return None
    try:
        return InterviewLastError.model_validate(interview.last_error)
    except ValidationError:
        logger.error("interview_last_error_invalid", interview_id=str(interview.id))
        return None


async def retry_interview(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """끝난 면접의 run·repo 조합으로 새 면접을 만든다. 생성 검사는 create_interview 그대로.

    허용 상태는 BE 명세대로 completed·abandoned. FE 문서는 '완료 상태가 아님'으로 적어
    다르다 (spec/frontend/features/report.md 계약 차이, PR 에서 명세 반영 확인).
    없거나 남의 면접은 존재를 알리지 않도록 404 (계약에 404 없음, PR 에서 확인).
    """
    row = await queries.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    if row is None:
        raise AppError(Reason.NOT_FOUND)
    original = row[0]
    if original.status not in ("completed", "abandoned"):
        raise AppError(Reason.ORIGINAL_NOT_COMPLETED)
    # ponytail: repo 행이 삭제되면 session_repositories 도 CASCADE 로 사라져 일부 삭제는
    # 알 수 없고 남은 repo 로 만든다. 전부 사라지면 아래에서 repository_unavailable.
    repository_ids = await queries.list_repository_ids(db, interview_id=interview_id)
    try:
        return await create_interview(
            db,
            redis,
            user_id=user_id,
            run_id=original.analysis_job_id,
            repository_ids=repository_ids,
            retry_of=interview_id,
        )
    except AppError as exc:
        # 원본 repo 가 private·접근 불가로 바뀌었거나 사라짐. 계약 reason 으로 바꾼다.
        if exc.reason in (Reason.INVALID_REPOSITORY, Reason.NO_REPOSITORY_SELECTED):
            raise AppError(Reason.REPOSITORY_UNAVAILABLE) from None
        raise


async def retry_prepare(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> None:
    """preparing_failed 면접을 preparing 으로 되돌리고 interview_prep 을 다시 넣는다.

    실패 단계부터 이어 하기는 worker 가 prepare_steps 를 보고 한다. 면접·선택 repo 는 유지.
    명세에 거절 응답이 없는 두 경우는 prep_failed 로 둔다 (PR 에서 명세 반영 여부 확인):
    - lastError.recoverable=false: 다시 해도 같은 이유로 실패한다 (FE 도 재선택만 보여준다).
    - 실패 뒤 같은 run 에 새 면접이 활성화됨: run 당 활성 1개 index 위반.
    """
    row = await queries.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    if row is None:
        raise AppError(Reason.SESSION_EXPIRED)
    interview = row[0]
    if interview.status == "preparing":
        raise AppError(Reason.PREP_IN_PROGRESS)
    if (
        interview.status != "preparing_failed"
        or (interview.last_error or {}).get("recoverable") is False
    ):
        raise AppError(Reason.PREP_FAILED)

    try:
        # 조건부 UPDATE — 동시 재시도 중 하나만 통과한다.
        updated = await db.scalar(
            update(InterviewSession)
            .where(
                InterviewSession.id == interview_id, InterviewSession.status == "preparing_failed"
            )
            .values(status="preparing")
            .returning(InterviewSession.id)
        )
    except IntegrityError as exc:
        await db.rollback()
        if _ACTIVE_PER_RUN_INDEX in str(exc.orig):
            raise AppError(Reason.PREP_FAILED) from None
        raise
    if updated is None:
        raise AppError(Reason.PREP_IN_PROGRESS)
    await db.commit()

    try:
        await redis.enqueue_job("interview_prep", str(interview_id))
    except RedisError:
        # job 없는 preparing 이 남으면 재시도도 새 면접도 막히므로 실패 상태로 되돌린다.
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == interview_id)
            .values(status="preparing_failed")
        )
        await db.commit()
        raise AppError(Reason.INTERNAL_ERROR) from None


def _remaining_seconds(interview: InterviewSession) -> int:
    """면접 제한 시간 - 경과. 시작 전이면 전체, 끝났으면 끝난 시각 기준."""
    total = get_settings().interview_duration_seconds
    if interview.started_at is None:
        return total
    end = interview.completed_at or interview.abandoned_at or datetime.now(UTC)
    return max(0, total - int((end - interview.started_at).total_seconds()))


# ★ rt:{sessionId} 와 rt:interview:{interviewId} 는 한 쌍이다. 같이 쓰고, TTL 연장·삭제도
#   같이 한다 (WS·이탈·종료 처리 포함). 역방향 키는 GET 이 sessionId 를 다시 찾는 데 쓴다.
def _rt_key(session_id: str) -> str:
    return f"rt:{session_id}"


def _reverse_key(interview_id: uuid.UUID) -> str:
    return f"rt:interview:{interview_id}"


async def _issue_session_id(redis: ArqRedis, *, interview_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """새 sessionId 로 두 키를 쓴다. 다른 요청이 방금 먼저 썼으면 그 값을 돌려준다 (두 탭 GET)."""
    session_id = secrets.token_urlsafe(32)
    await redis.set(
        _rt_key(session_id),
        json.dumps({"interviewId": str(interview_id), "userId": str(user_id)}),
        ex=REALTIME_SESSION_TTL_SECONDS,
    )
    reverse = _reverse_key(interview_id)
    if not await redis.set(reverse, session_id, ex=REALTIME_SESSION_TTL_SECONDS, nx=True):
        winner = await redis.get(reverse)
        if winner is not None:
            await redis.delete(_rt_key(session_id))
            return str(winner.decode())
        await redis.set(reverse, session_id, ex=REALTIME_SESSION_TTL_SECONDS)
    return session_id


async def _current_session_id(
    redis: ArqRedis, *, interview_id: uuid.UUID, user_id: uuid.UUID
) -> str:
    """살아 있는 sessionId 를 돌려준다. 만료됐거나 짝이 깨졌으면 새로 발급한다 (pipeline.md 4.4)."""
    reverse = _reverse_key(interview_id)
    found = await redis.get(reverse)
    if found is not None:
        session_id = str(found.decode())
        if await redis.exists(_rt_key(session_id)):
            return session_id
        await redis.delete(reverse)
    return await _issue_session_id(redis, interview_id=interview_id, user_id=user_id)
