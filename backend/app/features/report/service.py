"""리포트 lazy 생성·조회(200/202/409).
완료 면접에 답변 완료 턴이 있을 때만 생성한다. 생성 불가는 409 report_unavailable.
이전 생성 실패 이력의 409 는 저장 위치가 명세에 없어 합의 전까지 구현하지 않는다.
재생성·수동 재시도·이의제기는 Sprint 2다.
profile_summary 후속 enqueue 는 report_generate worker 몫이다.

docs/db-schema.md 리포트 절 / task-16
"""

import uuid
from datetime import UTC, datetime

from arq.connections import ArqRedis
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewReport, InterviewSession, JobPosting
from app.db.models.report import SCORE_KEYS
from app.features.report import queries
from app.features.report.schemas import (
    AgentFeedback,
    GeneratingResponse,
    ReportCoverage,
    ReportResponse,
    ReportTurn,
    ScoreItem,
)
from app.shared.enums import Reason

# docs/redis-keys.md: report generation lock. worker 가 끝나기 전에 풀리면 중복 enqueue 가 난다.
REPORT_LOCK_TTL_SECONDS = 5 * 60
RETRY_AFTER_SECONDS = 3
logger = get_logger(__name__)


async def get_report(
    db: AsyncSession, redis: ArqRedis, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> ReportResponse | GeneratingResponse:
    """리포트가 있으면 ReportResponse, 생성을 시작했거나 진행 중이면 GeneratingResponse.

    입력: 요청 사용자 id, interviewId. 없거나 남의 면접이면 not_found,
    생성할 수 없는 면접이면 report_unavailable.
    """
    row = await queries.get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    if row is None:
        raise AppError(Reason.NOT_FOUND)
    interview, posting = row

    report = await queries.get_report(db, interview_id=interview.id)
    if report is not None:
        return await _build_report(db, interview, posting, report)

    if interview.status != "completed":
        raise AppError(Reason.REPORT_UNAVAILABLE)
    if await queries.count_answered_turns(db, interview_id=interview.id) < 1:
        raise AppError(Reason.REPORT_UNAVAILABLE)
    # TODO 없이 보류: 이전 report_generate 실패 이력 → 409 는 합의 후 추가한다 (PR 본문 참고).
    return await _request_generation(redis, interview.id)


async def _request_generation(redis: ArqRedis, interview_id: uuid.UUID) -> GeneratingResponse:
    """lock 을 잡은 요청만 report_generate 를 enqueue 한다. 못 잡으면 이미 생성 중이다."""
    key = f"report:gen:{interview_id}"
    try:
        acquired = await redis.set(key, "1", nx=True, ex=REPORT_LOCK_TTL_SECONDS)
    except RedisError:
        raise AppError(Reason.INTERNAL_ERROR) from None
    if acquired:
        try:
            await redis.enqueue_job("report_generate", str(interview_id))
        except RedisError:
            # 풀지 않으면 job 없는 lock 때문에 5분간 202 만 돌려주게 된다.
            try:
                await redis.delete(key)
            except RedisError:
                logger.error("report_lock_release_failed", interview_id=str(interview_id))
            raise AppError(Reason.INTERNAL_ERROR) from None
    return GeneratingResponse(retry_after=RETRY_AFTER_SECONDS)


async def _build_report(
    db: AsyncSession, interview: InterviewSession, posting: JobPosting, report: InterviewReport
) -> ReportResponse:
    """저장된 리포트를 응답으로 만든다. 저장 형식이 어긋난 행은 internal_error 다."""
    scores = [
        ScoreItem(key=key, label=label, score=score)
        for key, label, score in await queries.list_scores(db, report_id=report.id)
    ]
    if {s.key for s in scores} != set(SCORE_KEYS):
        _corrupt(report, "scores")
    disagreed = await queries.list_disagreed_personas(db, report_id=report.id)
    try:
        feedbacks = [
            AgentFeedback(**item, disagreement_submitted=item.get("persona") in disagreed)
            for item in report.feedback_json
        ]
        coverage = ReportCoverage.model_validate(report.coverage_json)
    except (ValidationError, TypeError):
        _corrupt(report, "feedback_or_coverage")
    turns = await queries.list_turns(db, interview_id=interview.id)
    position = posting.position or ""
    return ReportResponse(
        interview_id=interview.id,
        position=position,
        position_label=" ".join(p for p in (posting.company_name, position) if p),
        total_score=round(sum(s.score for s in scores) / len(scores), 2),
        headline=report.headline,
        summary=report.summary,
        scores=scores,
        agent_feedbacks=feedbacks,
        coverage=coverage,
        turns=[
            ReportTurn(
                turn=t.turn_no, persona=t.persona, question=t.question_text, answer=t.answer_text
            )
            for t in turns
        ],
        repository_names=await queries.list_repository_names(db, interview_id=interview.id),
        completed_at=interview.completed_at or report.generated_at or datetime.now(UTC),
    )


def _corrupt(report: InterviewReport, part: str) -> None:
    logger.error("report_row_invalid", report_id=str(report.id), part=part)
    raise AppError(Reason.INTERNAL_ERROR)
