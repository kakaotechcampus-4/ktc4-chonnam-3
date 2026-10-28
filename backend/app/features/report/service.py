"""리포트 lazy 생성·조회(200/202/409).
완료 면접에 답변 완료 턴이 있을 때만 생성한다. 생성 불가는 409 report_unavailable.
이전 생성 실패 이력의 409 는 저장 위치가 명세에 없어 합의 전까지 구현하지 않는다.
재생성·수동 재시도·이의제기는 Sprint 2다.
생성(generate_report)과 profile_summary 후속 enqueue 는 report_generate worker 가 호출한다.

docs/db-schema.md 리포트 절 / task-16
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from typing import Literal, cast

import httpx
from arq.connections import ArqRedis
from devon_ai import contracts as c
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import (
    Evidence,
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    JdRequirement,
    JobPosting,
)
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
from app.integrations.llm.client import CallBudget, call_model
from app.llm_tasks.prompt_loader import load_active_prompt
from app.llm_tasks.report import (
    ModelCall,
    ReportDraft,
    ReportDraftInvalidError,
    ReportGenerator,
    ReportModuleUnavailableError,
    resolve_generator,
    validate_draft,
)
from app.shared.enums import Reason

# docs/redis-keys.md: report generation lock. worker 가 끝나기 전에 풀리면 중복 enqueue 가 난다.
REPORT_LOCK_TTL_SECONDS = 5 * 60
# 실패 이력: migration 없이 Redis 에 코드만 남긴다. 409 판정에는 아직 연결하지 않는다(합의 대기).
REPORT_FAIL_KEY = "report:fail:{interview_id}"
REPORT_PROMPT_TASK = "report"
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


type GenerateOutcome = Literal["created", "exists", "skipped"]


async def generate_report(
    sessions: async_sessionmaker[AsyncSession],
    *,
    interview_id: uuid.UUID,
    llm: LLMSettings,
    http_client: httpx.AsyncClient,
    generator: ReportGenerator | None = None,
) -> GenerateOutcome:
    """리포트를 생성해 저장한다. 이미 있으면 "exists", 생성 조건이 사라졌으면 "skipped".

    DB transaction 은 입력 수집과 저장에 각각 짧게만 쓰고 모델 호출 중에는 열어 두지 않는다.
    실패는 예외로 전파하며 호출자(worker)가 실패 이력과 lock 해제를 맡는다.
    """
    async with sessions.begin() as db:
        interview = await db.get(InterviewSession, interview_id)
        if interview is None:
            return "skipped"
        if await queries.get_report(db, interview_id=interview_id) is not None:
            return "exists"
        if interview.status != "completed":
            return "skipped"
        turns = await queries.list_answered_turns(db, interview_id=interview_id)
        if not turns:
            return "skipped"
        posting = await db.get(JobPosting, interview.job_posting_id)
        requirements = await queries.list_requirements(db, posting_id=interview.job_posting_id)
        evidences = await queries.list_turn_evidences(db, interview_id=interview_id)
        prompt = await load_active_prompt(db, REPORT_PROMPT_TASK)
        payload = _build_payload(posting, turns, evidences, requirements)
        coverage = _coverage(requirements, turns)
        turn_ids = {t.turn_no: t.id for t in turns}

    generate = generator or resolve_generator()
    model_call = cast(
        ModelCall,
        partial(
            call_model,
            api_key=llm.openai_api_key,
            base_url=llm.llm_base_url,
            http_client=http_client,
            budget=CallBudget(),
        ),
    )
    raw = await generate(payload, prompt=prompt, limits=llm.call_limits(), model_call=model_call)
    draft = validate_draft(raw)
    rows = _score_rows(draft, turn_ids)

    async with sessions.begin() as db:
        saved = await queries.insert_report(
            db,
            interview_id=interview_id,
            values={
                "headline": draft.headline,
                "summary": draft.summary,
                "total_score": draft.total_score,
                "feedback_json": [
                    {
                        "persona": f.persona,
                        "tags": list(f.tags),
                        "strengths": list(f.strengths),
                        "improvements": list(f.improvements),
                    }
                    for f in draft.feedbacks
                ],
                "coverage_json": coverage,
                "model": prompt.model,
                "prompt_version": prompt.version,
            },
            scores=rows,
            generated_at=datetime.now(UTC),
        )
    return "created" if saved else "exists"


def _build_payload(
    posting: JobPosting | None,
    turns: list[InterviewTurn],
    evidences: Mapping[uuid.UUID, list[tuple[str, Evidence]]],
    requirements: list[JdRequirement],
) -> dict[str, object]:
    """AI 모듈 입력. 점수 key 는 고정 6개만 전달하고 score_criteria 세부 기준은 넣지 않는다."""
    return {
        "score_keys": list(SCORE_KEYS),
        "position": posting.position if posting else None,
        "company_name": posting.company_name if posting else None,
        "requirements": [
            {"id": str(r.id), "category": r.category, "text": r.text} for r in requirements
        ],
        "turns": [
            {
                "turn_no": t.turn_no,
                "persona": t.persona,
                "question": t.question_text,
                "answer": t.answer_text,
                "question_contract": t.question_contract,
                "analysis": t.analysis,
                "decision": t.decision,
                "jd_requirement_ids": [str(i) for i in t.jd_requirement_ids],
                "evidences": [
                    {
                        "usage": usage,
                        "source_type": e.source_type,
                        "path": e.path,
                        "start_line": e.start_line,
                        "end_line": e.end_line,
                        "snippet": e.snippet,
                        "summary": e.summary,
                    }
                    for usage, e in evidences.get(t.id, [])
                ],
            }
            for t in turns
        ],
    }


def _coverage(requirements: list[JdRequirement], turns: list[InterviewTurn]) -> dict[str, object]:
    """질문이 실제로 다룬 요구사항 수. 답변 완료 턴의 jd_requirement_ids 합집합으로 센다."""
    asked = {i for t in turns for i in t.jd_requirement_ids}
    uncovered = [r.text for r in requirements if r.id not in asked]
    return {
        "totalRequirements": len(requirements),
        "coveredRequirements": len(requirements) - len(uncovered),
        "uncoveredRequirements": uncovered,
    }


def _score_rows(draft: ReportDraft, turn_ids: Mapping[int, uuid.UUID]) -> list[dict[str, object]]:
    """ReportScore 값. 근거 turn 번호가 답변 완료 턴이 아니면 보정하지 않고 실패시킨다."""
    rows: list[dict[str, object]] = []
    for key in SCORE_KEYS:
        item = draft.scores[key]
        if any(n not in turn_ids for n in item.evidence_turn_nos):
            raise ReportDraftInvalidError(f"scores.{key}.evidence_turn_nos")
        rows.append(
            {
                "score_key": key,
                "score": item.score,
                "reason": item.reason,
                "evidence_turn_ids": [turn_ids[n] for n in item.evidence_turn_nos],
            }
        )
    return rows


def failure_code(error: BaseException) -> str:
    """실패 이력에 남길 코드. 원문 예외 메시지는 저장하지 않는다."""
    if isinstance(error, ReportModuleUnavailableError):
        return "report_module_unavailable"
    if isinstance(error, ReportDraftInvalidError):
        return "report_invalid"
    if isinstance(error, c.ContractError):
        return "llm_failed"
    return "internal_error"


async def record_failure(redis: ArqRedis, interview_id: uuid.UUID, code: str) -> None:
    """실패 이력을 Redis 에 남긴다. 기록 실패는 로그만 남기고 삼킨다."""
    try:
        await redis.set(REPORT_FAIL_KEY.format(interview_id=interview_id), code)
    except RedisError:
        logger.error("report_failure_record_failed", interview_id=str(interview_id), code=code)


async def release_lock(redis: ArqRedis, interview_id: uuid.UUID) -> None:
    """report:gen lock 을 푼다. 풀지 못하면 TTL 이 끝날 때까지 202 만 나간다."""
    try:
        await redis.delete(f"report:gen:{interview_id}")
    except RedisError:
        logger.error("report_lock_release_failed", interview_id=str(interview_id))


async def get_interview_user_id(db: AsyncSession, interview_id: uuid.UUID) -> uuid.UUID:
    """profile_summary enqueue 용 소유자 id. 면접이 사라졌으면 예외로 알린다."""
    interview = await db.get(InterviewSession, interview_id)
    if interview is None:
        raise LookupError("interview not found")
    return interview.user_id
