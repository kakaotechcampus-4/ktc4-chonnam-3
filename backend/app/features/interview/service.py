"""세션 생성 / 동시 면접 제한 / sessionId 발급.
★ job_posting_id 가 NOT NULL 이다 (공고 필수).
★ status = preparing / preparing_failed / in_progress / completed / abandoned. paused 없음.
★ answer_mode = 새 세션 voice(기본값), 기존 text 세션은 CHECK로 허용한다 (0007, migration 0006).
★ 명시적 이탈·레포 재선택만 status='abandoned' + abandoned_at_turn으로 처리한다.
  WS 끊김은 재연결 대상이며 미답변 턴은 asked로 남는다. 자동 timeout 이탈 판정은 없다.
  실제 상태 저장·연결은 구현 대기다.

생성 검사 기준은 spec/backend/features/interview.md "생성 검사 해석".

확정본 §5 interview_sessions / task-13
"""

import json
import secrets
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import cast

from arq.connections import ArqRedis
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewSession, SessionRepository
from app.db.models import InterviewTurn as InterviewTurnRow
from app.features.interview import queries
from app.features.interview.queue import enqueue_interview_prep
from app.features.interview.schemas import (
    InterviewDetailResponse,
    InterviewLastError,
    InterviewTurn,
)
from app.features.interview.turn_position import TurnPosition, turn_position
from app.shared.enums import Reason
from app.shared.events import commit_events, record_event

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
    except RedisError:
        # sessionId 를 못 받은 클라이언트의 preparing 행은 같은 run 의 새 면접을 막으므로 되돌린다.
        try:
            await db.delete(interview)
            await db.commit()
        except SQLAlchemyError:
            # 되돌리기에 실패한 행도 아래 준비 reaper 가 enqueue 하거나 만료 처리한다.
            logger.error("interview_create_rollback_failed", interview_id=str(interview_id))
        raise AppError(Reason.INTERNAL_ERROR) from None
    # enqueue 실패는 행을 지우지 않는다. preparing 행이 복구 근거이고 reaper 가 재등록한다.
    if not await enqueue_interview_prep(redis, interview_id):
        logger.warning("interview_create_enqueue_deferred", interview_id=str(interview_id))
    # 선택은 이미 commit 됐으므로 큐 접수 여부와 무관하게 1회 남긴다.
    # sessionId 발급 실패의 되돌리기 경로는 위에서 raise 하므로 이벤트가 새지 않는다.
    await record_event(
        db,
        "repo_selected",
        user_id=user_id,
        analysis_job_id=run_id,
        interview_session_id=interview_id,
        payload={"repositoryCount": len(repository_ids)},
    )
    await commit_events(db)
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
    from app.features.interview.question_retry import availability, progress

    can_retry, retry_count = await availability(db, interview)
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
        remaining_seconds=_remaining_seconds(interview, turns),
        turns=[
            _detail_turn(t, [(item.turn_no, item.depth, item.parent_turn_no) for item in turns])
            for t in turns
        ],
        # openapi: preparing_failed 일 때만 내려준다.
        last_error=_last_error(interview) if interview.status == "preparing_failed" else None,
        can_retry_question=can_retry,
        question_retry_count=retry_count,
        question_retry_state=progress(interview),
    )


def _detail_turn(turn: InterviewTurnRow, positions: list[TurnPosition]) -> InterviewTurn:
    main_index, follow_up_depth = turn_position(positions, turn.turn_no)
    return InterviewTurn(
        turn=turn.turn_no,
        persona=turn.persona,
        question=turn.question_text,
        answer=turn.answer_text,
        main_index=main_index,
        follow_up_depth=follow_up_depth,
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
    """완료 또는 시작 후 중단한 면접의 run·repo 조합으로 새 면접을 만든다(공통 0009)."""
    row = await queries.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    if row is None:
        raise AppError(Reason.NOT_FOUND)
    original = row[0]
    if original.status != "completed" and not (
        original.status == "abandoned" and original.started_at is not None
    ):
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


_ABANDON_REALTIME = """
local session = redis.call('GET', KEYS[1])
if session then
    local owner = redis.call('GET', 'ws:lock:' .. session)
    if owner then redis.call('PUBLISH', 'ws:replace:' .. session, owner) end
    redis.call('DEL', 'rt:' .. session, KEYS[1])
end
redis.call('DEL', KEYS[2])
return 1
"""


async def abandon_interview(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> None:
    """명시 중단을 확정한다. 재호출은 같은 기록을 유지하며 연결 정리만 재시도한다."""
    interview = await db.scalar(
        select(InterviewSession)
        .where(InterviewSession.id == interview_id, InterviewSession.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if interview is None:
        raise AppError(Reason.NOT_FOUND)
    if interview.status not in ("in_progress", "preparing_failed", "abandoned"):
        raise AppError(Reason.ALREADY_COMPLETED)
    if interview.status != "abandoned":
        # T2~T4와 같은 세션 잠금으로 순서를 정한다. 답변 대기 중인 현재 질문도 포함한다.
        interview.status = "abandoned"
        interview.abandoned_at = datetime.now(UTC)
        interview.abandoned_at_turn = interview.current_turn
    # 영구 상태를 먼저 확정하므로 늦은 LLM·Tool 결과는 기존 상태 재검사에서 폐기된다.
    await db.commit()
    try:
        execute = cast(Callable[..., Awaitable[object]], redis.execute_command)
        await execute(
            "EVAL",
            _ABANDON_REALTIME,
            2,
            realtime_interview_key(interview_id),
            f"iv:ctx:{interview_id}",
        )
    except RedisError:
        # Redis 장애가 중단을 되돌리지는 않는다. 응답 실패 후 재호출로 연결 정리를 복구한다.
        logger.warning("interview_abandon_realtime_cleanup_failed", interview_id=str(interview_id))
        raise AppError(Reason.INTERNAL_ERROR) from None


async def retry_prepare(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> None:
    """preparing_failed 면접을 preparing 으로 되돌리고 interview_prep 을 다시 넣는다.

    실패 단계부터 이어 하기는 worker 가 prepare_steps 를 보고 한다. 면접·선택 repo 는 유지.
    명세에 거절 응답이 없는 두 경우 (#121 1-4):
    - lastError.recoverable=false: prep_failed. 다시 해도 같은 이유로 실패한다
      (FE 도 재선택만 보여준다).
    - 실패 뒤 같은 run 에 새 면접이 활성화됨(run 당 활성 1개 index 위반): session_limit_exceeded.
      prep_failed 면 FE 가 GET 을 다시 불러 재시도 버튼이 반복되므로 reason 을 나눈다.
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
            raise AppError(Reason.SESSION_LIMIT_EXCEEDED) from None
        raise
    if updated is None:
        raise AppError(Reason.PREP_IN_PROGRESS)
    await db.commit()

    try:
        await redis.enqueue_job("interview_prep", str(interview_id))
    except RedisError:
        # job 없는 preparing 이 남으면 재시도도 새 면접도 막히므로 실패 상태로 되돌린다.
        try:
            await db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == interview_id, InterviewSession.status == "preparing")
                .values(status="preparing_failed")
            )
            await db.commit()
        except SQLAlchemyError:
            logger.error("interview_prepare_retry_rollback_failed", interview_id=str(interview_id))
        raise AppError(Reason.INTERNAL_ERROR) from None


def _remaining_seconds(interview: InterviewSession, turns: Sequence[InterviewTurnRow]) -> int:
    """면접 제한 시간 - (경과 - 질문 생성 대기). 시작 전이면 전체, 끝났으면 끝난 시각 기준.

    질문 생성 대기는 답변을 저장한 시각부터 다음 질문을 저장한 시각까지다(#246).
    다음 질문이 아직 없는 구간은 끝난 시각(진행 중이면 지금)까지 센다. turns 는 turn_no 순.
    """
    total = get_settings().interview_duration_seconds
    started = interview.started_at
    if started is None:
        return total
    end = interview.completed_at or interview.abandoned_at or datetime.now(UTC)
    paused = 0.0
    for index, turn in enumerate(turns):
        if turn.answered_at is None:
            continue
        following = turns[index + 1] if index + 1 < len(turns) else None
        if following is None:
            resume = end
        elif following.asked_at is None:
            continue  # 질문 저장 시각을 모르면 정지로 보지 않는다.
        else:
            resume = min(following.asked_at, end)
        paused += max(0.0, (resume - max(turn.answered_at, started)).total_seconds())
    return max(0, total - int((end - started).total_seconds() - paused))


# ★ rt:{sessionId} 와 rt:interview:{interviewId} 는 한 쌍이다. 같이 쓰고, TTL 연장·삭제도
#   같이 한다 (WS·이탈·종료 처리 포함). 역방향 키는 GET 이 sessionId 를 다시 찾는 데 쓴다.
def realtime_session_key(session_id: str) -> str:
    """REST 발급과 WS 소유권 검사가 공유하는 실시간 세션 키다."""
    return f"rt:{session_id}"


def realtime_interview_key(interview_id: uuid.UUID) -> str:
    """영구 면접 ID에서 현재 실시간 세션을 찾는 역방향 키다."""
    return f"rt:interview:{interview_id}"


async def _issue_session_id(redis: ArqRedis, *, interview_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """새 sessionId 로 두 키를 쓴다. 다른 요청이 방금 먼저 썼으면 그 값을 돌려준다 (두 탭 GET)."""
    session_id = secrets.token_urlsafe(32)
    await redis.set(
        realtime_session_key(session_id),
        json.dumps({"interviewId": str(interview_id), "userId": str(user_id)}),
        ex=REALTIME_SESSION_TTL_SECONDS,
    )
    reverse = realtime_interview_key(interview_id)
    if not await redis.set(reverse, session_id, ex=REALTIME_SESSION_TTL_SECONDS, nx=True):
        winner = await redis.get(reverse)
        if winner is not None:
            await redis.delete(realtime_session_key(session_id))
            return str(winner.decode())
        await redis.set(reverse, session_id, ex=REALTIME_SESSION_TTL_SECONDS)
    return session_id


async def _current_session_id(
    redis: ArqRedis, *, interview_id: uuid.UUID, user_id: uuid.UUID
) -> str:
    """살아 있는 sessionId 를 돌려준다. 만료됐거나 짝이 깨졌으면 새로 발급한다 (pipeline.md 4.4)."""
    reverse = realtime_interview_key(interview_id)
    found = await redis.get(reverse)
    if found is not None:
        session_id = str(found.decode())
        if await redis.exists(realtime_session_key(session_id)):
            return session_id
        await redis.delete(reverse)
    return await _issue_session_id(redis, interview_id=interview_id, user_id=user_id)
