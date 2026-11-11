"""/interviews REST — 생성, 조회, 준비 재시도, 재도전.
준비 실패 재시도는 REST POST /interviews/{id}/prepare/retry이며 WS 메시지가 아니다.
main.py 등록은 interview_prep 워커 연결(AI task-06) 때 한다.
그 전에 열면 면접이 preparing 에 머문다.

docs/layer-rules.md 1절 / task-13
"""

import asyncio
import uuid
from functools import partial
from typing import Annotated

from devon_ai.contracts import AttemptMetadata
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.session import get_db
from app.features.interview import service
from app.features.interview.question_audio import (
    PronounceFragments,
    PronunciationStatus,
    QuestionAudioService,
    load_pronunciation_prompt,
    load_question,
    load_question_pronunciation,
)
from app.features.interview.question_audio_records import record_question_pronunciation
from app.features.interview.schemas import (
    CreateInterviewRequest,
    CreateInterviewResponse,
    InterviewDetailResponse,
    QuestionRetryRequest,
    QuestionRetryResponse,
)
from app.features.interview.tts_budget import RedisCharacterBudget
from app.integrations.tts.google import (
    FINALIZATION_TIMEOUT_SECONDS,
    BudgetedSpeechSynthesizer,
    GoogleTTSClient,
    TtsError,
)
from app.llm_tasks.question_pronunciation import pronounce_fragments
from app.shared.enums import Reason

router = APIRouter(prefix="/interviews", tags=["interviews"])
Database = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
logger = get_logger(__name__)


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


@router.get("/{interview_id}/turns/{turn_no}/question-audio", response_class=Response)
async def get_question_audio(
    interview_id: str, turn_no: int, request: Request, db: Database, user: CurrentUser
) -> Response:
    """확정된 본인 질문만 합성한다. 음성 실패는 질문·답변·면접 상태를 바꾸지 않는다."""
    user_id = user.id
    try:
        source = await load_question(
            db,
            user_id=user_id,
            interview_id=_parse_id(interview_id, Reason.NOT_FOUND),
            turn_no=turn_no,
        )
        # 합성 대기 동안 읽기 트랜잭션을 유지하지 않는다. 반환 직전에 다시 확인한다.
        await db.rollback()
    except (SQLAlchemyError, OSError, TimeoutError):
        raise AppError(Reason.NOT_READY) from None

    async def still_current() -> bool:
        try:
            latest = await load_question(
                db, user_id=user_id, interview_id=source.interview_id, turn_no=source.turn_no
            )
            return latest == source
        except AppError:
            return False
        except (SQLAlchemyError, OSError, TimeoutError):
            raise TtsError("source_check_unavailable") from None
        finally:
            await db.rollback()

    attempts: list[AttemptMetadata] = []
    try:
        app_settings = request.app.state.settings
        settings = app_settings.require_tts()
        if settings.monthly_character_limit is None or not settings.budget_project:
            raise TtsError("budget_unconfigured")
        budget = RedisCharacterBudget(
            request.app.state.redis,
            project=settings.budget_project,
            monthly_limit=settings.monthly_character_limit,
        )
        injected = getattr(request.app.state, "tts_client", None)
        synthesizer = (
            GoogleTTSClient(settings, budget=budget)
            if injected is None
            else BudgetedSpeechSynthesizer(injected, settings, budget)
        )
        pronunciation = await load_question_pronunciation(db, app_settings, text=source.text)

        async def load_pronounce() -> PronounceFragments:
            llm, prompt = await load_pronunciation_prompt(db, pronunciation)
            return partial(pronounce_fragments, llm, prompt, attempt_sink=attempts)

        service = QuestionAudioService(
            request.app.state.redis,
            synthesizer,
            settings,
            pronunciation_identity=pronunciation.identity,
            load_pronounce=load_pronounce
            if pronunciation.status is PronunciationStatus.READY
            else None,
        )
        try:
            async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
                if pronunciation.status is PronunciationStatus.TEMP_UNAVAILABLE:
                    identity = await service.known_identity(source, pronunciation.model)
                else:
                    await service.remember_identity(source, pronunciation)
                    identity = None
            if pronunciation.status is PronunciationStatus.TEMP_UNAVAILABLE:
                if identity is None:
                    raise TtsError("pronunciation_unavailable")
                cached_service = QuestionAudioService(
                    request.app.state.redis, synthesizer, settings, pronunciation_identity=identity
                )
                audio = await cached_service.get_cached(source, check_current=still_current)
                if audio is None:
                    raise TtsError("pronunciation_unavailable")
            else:
                audio = await service.get(source, check_current=still_current)
        finally:
            await record_question_pronunciation(request.app.state.session_factory, source, attempts)
        async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
            if not await still_current():
                raise TtsError("source_changed")
    except (TtsError, ValueError, SQLAlchemyError, OSError, TimeoutError) as exc:
        logger.warning(
            "question_audio_unavailable",
            interview_id=str(source.interview_id),
            turn=turn_no,
            exception_type=type(exc).__name__,
        )
        raise AppError(
            Reason.NOT_READY, message="질문 음성을 재생할 수 없습니다. 질문 텍스트를 확인해 주세요."
        ) from None
    return Response(
        audio.data,
        media_type=audio.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{interview_id}/start", status_code=status.HTTP_204_NO_CONTENT)
async def start_interview(interview_id: str, db: Database, user: CurrentUser) -> None:
    """[면접 시작하기] 클릭. 이 시각부터 제한 시간이 흐른다 (#259)."""
    await service.start_interview(
        db, user_id=user.id, interview_id=_parse_id(interview_id, Reason.NOT_FOUND)
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


@router.post("/{interview_id}/question/retry", response_model=QuestionRetryResponse)
async def retry_question(
    interview_id: str,
    body: QuestionRetryRequest,
    request: Request,
    db: Database,
    user: CurrentUser,
) -> QuestionRetryResponse:
    from app.features.interview.question_retry import retry_question as execute_retry

    user_id = user.id
    # 인증 조회의 트랜잭션을 닫고 전용 실행 세션으로 유한 재생성을 진행한다.
    await db.rollback()
    return await execute_retry(
        request.app.state.session_factory,
        request.app.state.redis,
        user_id=user_id,
        interview_id=_parse_id(interview_id, Reason.NOT_FOUND),
        request_id=body.request_id,
        settings=request.app.state.settings.require_llm(),
        http_client=request.app.state.http_client,
    )


@router.post("/{interview_id}/abandon", status_code=status.HTTP_204_NO_CONTENT)
async def abandon_interview(
    interview_id: str, request: Request, db: Database, user: CurrentUser
) -> None:
    await service.abandon_interview(
        db,
        request.app.state.redis,
        user_id=user.id,
        interview_id=_parse_id(interview_id, Reason.NOT_FOUND),
    )


@router.post(
    "/{interview_id}/retry",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateInterviewResponse,
)
async def retry_interview(
    interview_id: str, request: Request, db: Database, user: CurrentUser
) -> CreateInterviewResponse:
    new_id, session_id = await service.retry_interview(
        db,
        request.app.state.redis,
        user_id=user.id,
        interview_id=_parse_id(interview_id, Reason.NOT_FOUND),
    )
    return CreateInterviewResponse(session_id=session_id, interview_id=new_id)


def _parse_id(interview_id: str, missing: Reason) -> uuid.UUID:
    """UUID 가 아닌 id 도 없는 면접이다. 계약에 400 이 없어 그 route 의 '없음' reason 으로 낸다."""
    try:
        return uuid.UUID(interview_id)
    except ValueError:
        raise AppError(missing) from None
