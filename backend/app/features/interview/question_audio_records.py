"""발음 호출 기록은 별도 세션에서 유한 시간만 기다리며 음성 응답과 분리한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

from devon_ai.contracts import AttemptMetadata
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.db.models import LLMCallRecord
from app.integrations.tts.google import complete_audio_finalization
from app.llm_tasks.question_pronunciation import QUESTION_PRONUNCIATION_TASK

if TYPE_CHECKING:
    from app.features.interview.question_audio import AudioQuestion

logger = get_logger(__name__)


async def record_question_pronunciation(
    session_factory: async_sessionmaker[AsyncSession],
    question: AudioQuestion,
    attempts: list[AttemptMetadata],
) -> None:
    if not attempts:
        return
    last = attempts[-1]

    async def persist() -> None:
        # 세션 생성·커밋·종료까지 기존 1초 마무리 상한에 포함한다.
        async with session_factory() as db, db.begin():
            db.add(
                LLMCallRecord(
                    interview_session_id=question.interview_id,
                    turn_id=question.turn_id,
                    turn_no=question.turn_no,
                    task_name=QUESTION_PRONUNCIATION_TASK,
                    attempts=[
                        {
                            "attempt": item.attempt,
                            "provider": item.provider,
                            "model": item.model,
                            "prompt_version": item.prompt_version,
                            "schema_version": item.schema_version,
                            "latency_ms": item.latency_ms,
                            "input_tokens": item.input_tokens,
                            "output_tokens": item.output_tokens,
                            "error_stage": item.error_stage,
                            "error_code": item.error_code,
                        }
                        for item in attempts
                    ],
                    failure={"stage": last.error_stage, "error_code": last.error_code}
                    if last.error_code
                    else None,
                )
            )

    try:
        await complete_audio_finalization(persist)
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        # 미확인 사용량은 0으로 추정하지 않으며 원문·접속 정보는 로그에 넣지 않는다.
        input_tokens = [item.input_tokens for item in attempts]
        output_tokens = [item.output_tokens for item in attempts]
        logger.warning(
            "question_pronunciation_record_unavailable",
            interview_id=str(question.interview_id),
            turn_no=question.turn_no,
            attempt_count=len(attempts),
            input_tokens=sum(value for value in input_tokens if value is not None)
            if None not in input_tokens
            else None,
            output_tokens=sum(value for value in output_tokens if value is not None)
            if None not in output_tokens
            else None,
            exception_type=type(exc).__name__,
        )
