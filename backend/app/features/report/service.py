"""리포트 lazy 생성·조회(200/202/409).
완료 면접에 답변 완료 턴이 있을 때만 생성한다. 생성 불가는 409 report_unavailable.
이전 생성 실패 이력(report:fail:{id}, report_generate worker 가 기록)이 있으면 자동 재생성 없이 409.
실패 후에는 명시 재시도만 허용하고, 성공본은 검토 승인·버전 확인을 거친 재평가만 교체한다.
생성(generate_report)과 profile_summary 후속 enqueue 는 report_generate worker 가 호출한다.

docs/db-schema.md 리포트 절 / task-16
"""

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Literal, NoReturn, cast

import httpx
from arq.connections import ArqRedis
from devon_ai import contracts as c
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import delete, select
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
    ReportDisagreement,
    ReportScore,
)
from app.db.models.report import SCORE_KEYS, ReportGenerationRequest
from app.features.interview.turn_position import turn_position
from app.features.report import generation, queries, revisions
from app.features.report.history import enrich_report_history
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
    ReportRubricUnavailableError,
    resolve_generator,
    total_score,
    validate_draft,
)
from app.shared.enums import Reason

# docs/redis-keys.md: report generation lock. worker 가 끝나기 전에 풀리면 중복 enqueue 가 난다.
REPORT_LOCK_TTL_SECONDS = generation.LOCK_SECONDS
# 실패 이력: report_generate worker 가 코드를 남긴다. TTL 이 없어 자동 재생성이 없다.
REPORT_FAIL_KEY = "report:fail:{interview_id}"
# AI 모듈이 서술(report)과 점수 판정(report_score) 두 task 를 쓴다. 둘 다 활성이어야 한다.
REPORT_PROMPT_TASKS = ("report", "report_score")
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
    if await _has_failure_history(redis, interview.id):
        raise AppError(Reason.REPORT_UNAVAILABLE)
    await generation.enqueue(db, redis, interview_id=interview.id, user_id=user_id)
    return GeneratingResponse(retry_after=RETRY_AFTER_SECONDS)


async def _has_failure_history(redis: ArqRedis, interview_id: uuid.UUID) -> bool:
    try:
        return bool(await redis.exists(REPORT_FAIL_KEY.format(interview_id=interview_id)))
    except RedisError:
        raise AppError(Reason.INTERNAL_ERROR) from None


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
    disagreed = await queries.list_disagreed_personas(
        db, report_id=report.id, revision=report.current_revision
    )
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
    # 면접 진행·재접속·리포트가 같은 DB depth를 같은 질문 위치로 표시한다.
    positions = [(t.turn_no, t.depth) for t in turns]
    response_turns = []
    for turn in turns:
        main_index, follow_up_depth = turn_position(positions, turn.turn_no)
        response_turns.append(
            ReportTurn(
                turn=turn.turn_no,
                persona=turn.persona,
                question=turn.question_text,
                answer=turn.answer_text,
                main_index=main_index,
                follow_up_depth=follow_up_depth,
            )
        )
    return ReportResponse(
        interview_id=interview.id,
        revision=report.current_revision,
        position=position,
        position_label=" ".join(p for p in (posting.company_name, position) if p),
        total_score=total_score([int(s.score) for s in scores]),
        headline=report.headline,
        summary=report.summary,
        scores=scores,
        agent_feedbacks=feedbacks,
        coverage=coverage,
        turns=response_turns,
        repository_names=await queries.list_repository_names(db, interview_id=interview.id),
        completed_at=interview.completed_at or report.generated_at or datetime.now(UTC),
    )


def _corrupt(report: InterviewReport, part: str) -> NoReturn:
    logger.error("report_row_invalid", report_id=str(report.id), part=part)
    raise AppError(Reason.INTERNAL_ERROR)


type GenerateOutcome = Literal["created", "revised", "exists", "skipped"]


async def _read_generation_input(
    db: AsyncSession,
    interview: InterviewSession,
) -> tuple[dict[str, object], dict[str, c.PromptSpec], dict[int, uuid.UUID], dict[str, object]]:
    turns = await queries.list_report_turns(db, interview_id=interview.id)
    posting = await db.get(JobPosting, interview.job_posting_id)
    requirements = await queries.list_requirements(db, posting_id=interview.job_posting_id)
    evidences = await queries.list_turn_evidences(db, interview_id=interview.id)
    prompts = {name: await load_active_prompt(db, name) for name in REPORT_PROMPT_TASKS}
    rubrics = await queries.list_active_rubrics(db)
    if set(rubrics) != set(SCORE_KEYS):
        raise ReportRubricUnavailableError(",".join(sorted(rubrics)))
    payload = await enrich_report_history(
        db, interview, turns, _build_payload(posting, turns, evidences, requirements, rubrics)
    )
    answered = await queries.list_answered_turns(db, interview_id=interview.id)
    return payload, prompts, {t.turn_no: t.id for t in turns}, _coverage(requirements, answered)


def _input_snapshot(
    payload: dict[str, object], prompts: dict[str, c.PromptSpec], llm: LLMSettings
) -> tuple[str, dict[str, object]]:
    snapshot = {
        "payload": payload,
        "prompts": {name: asdict(p) for name, p in prompts.items()},
        "task_limits": {name: asdict(llm.call_limits(name)) for name in prompts},
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest(), json.loads(encoded)


def _draft_values(
    draft: ReportDraft, coverage: dict[str, object], prompts: dict[str, c.PromptSpec]
) -> dict[str, object]:
    return {
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
        "model": prompts[REPORT_PROMPT_TASKS[0]].model,
        "prompt_version": "+".join(prompts[name].version for name in REPORT_PROMPT_TASKS),
    }


async def generate_report(
    sessions: async_sessionmaker[AsyncSession],
    *,
    interview_id: uuid.UUID,
    llm: LLMSettings,
    http_client: httpx.AsyncClient | None,
    generator: ReportGenerator | None = None,
    generation_request_id: uuid.UUID | None = None,
) -> GenerateOutcome:
    """원문 입력은 짧게 읽고 모델을 호출한다. 명시 승인·CAS 없이 성공본을 바꾸지 않는다."""
    attempts: list[dict[str, object]] = []
    try:
        async with sessions.begin() as db:
            interview = await db.get(InterviewSession, interview_id, with_for_update=True)
            if interview is None or interview.status != "completed":
                return "skipped"
            request = (
                await db.get(ReportGenerationRequest, generation_request_id, with_for_update=True)
                if generation_request_id is not None
                else None
            )
            if generation_request_id is not None and (
                request is None
                or request.interview_session_id != interview_id
                or request.status != "running"
                or request.expires_at <= datetime.now(UTC)
            ):
                return "skipped"
            existing = await queries.get_report(db, interview_id=interview_id)
            reassessment = request is not None and request.mode == "reassessment"
            if existing is not None and not reassessment:
                return "exists"
            if (
                request is not None
                and reassessment
                and (existing is None or existing.current_revision != request.expected_revision)
            ):
                assert request is not None
                request.status, request.error_code = "stale", "report_revision_changed"
                return "skipped"
            if not await queries.count_answered_turns(db, interview_id=interview_id):
                return "skipped"
            payload, prompts, turn_ids, coverage = await _read_generation_input(db, interview)
            fingerprint, snapshot = _input_snapshot(payload, prompts, llm)
            if request is not None:
                request.input_fingerprint, request.input_snapshot = fingerprint, snapshot

        def model_call_factory() -> ModelCall:
            budget = CallBudget()

            async def invoke(
                request: c.ModelRequest, validator: Callable[[object], object]
            ) -> c.ModelResult[object]:
                request = replace(request, limits=llm.call_limits(request.prompt.task_name))
                output = await call_model(
                    request,
                    validator,
                    api_key=llm.openai_api_key,
                    base_url=llm.llm_base_url,
                    http_client=http_client,
                    budget=budget,
                )
                attempts.append(
                    {
                        "task": request.prompt.task_name,
                        "failure": asdict(output.failure) if output.failure else None,
                        "attempts": [asdict(item) for item in output.attempts],
                    }
                )
                return output

            return invoke

        raw = await (generator or resolve_generator())(
            payload,
            prompts=prompts,
            limits=llm.call_limits(prompts["report"].task_name),
            model_call_factory=model_call_factory,
        )
        draft = validate_draft(raw)
        rows = _score_rows(draft, turn_ids)
        values = _draft_values(draft, coverage, prompts)
        for call in attempts:
            if call.get("task") == "report":
                for metadata in cast(list[dict[str, object]], call["attempts"]):
                    if metadata.get("error_stage") is None and isinstance(
                        metadata.get("model"), str
                    ):
                        values["model"] = metadata["model"]
        async with sessions.begin() as db:
            interview = await db.get(InterviewSession, interview_id, with_for_update=True)
            request = (
                await db.get(ReportGenerationRequest, generation_request_id, with_for_update=True)
                if generation_request_id is not None
                else None
            )
            if generation_request_id is not None:
                if request is not None:
                    request.attempts = attempts
                if request is None or request.status != "running":
                    return "skipped"
            valid = interview is not None and interview.status == "completed"
            if valid and request is not None:
                assert interview is not None
                current, active_prompts, _, _ = await _read_generation_input(db, interview)
                valid = request.expires_at > datetime.now(UTC) and (
                    _input_snapshot(current, active_prompts, llm)[0] == fingerprint
                )
            if not valid:
                if request is not None:
                    request.status, request.error_code = "stale", "report_input_changed"
                return "skipped"
            if reassessment:
                assert request is not None
                existing = await db.scalar(
                    select(InterviewReport)
                    .where(InterviewReport.interview_session_id == interview_id)
                    .with_for_update()
                )
                review = await db.get(
                    ReportDisagreement, request.disagreement_id, with_for_update=True
                )
                if (
                    existing is None
                    or existing.current_revision != request.expected_revision
                    or review is None
                    or review.status != "approved"
                    or review.source_revision != request.expected_revision
                ):
                    request.status, request.error_code = "stale", "report_revision_changed"
                    return "skipped"
                await revisions.preserve(db, existing)
                for name, value in values.items():
                    setattr(existing, name, value)
                existing.current_revision += 1
                existing.generated_at = datetime.now(UTC)
                await db.execute(delete(ReportScore).where(ReportScore.report_id == existing.id))
                db.add_all(ReportScore(report_id=existing.id, **row) for row in rows)
                await db.flush()
                await revisions.preserve(db, existing)
                review.status, review.applied_revision = "applied", existing.current_revision
                outcome: GenerateOutcome = "revised"
            else:
                saved = await queries.insert_report(
                    db,
                    interview_id=interview_id,
                    values=values,
                    scores=rows,
                    generated_at=datetime.now(UTC),
                )
                outcome = "created" if saved else "exists"
            if outcome in {"created", "revised"}:
                from app.features.profile.refresh_outbox import ensure_request

                report = await db.scalar(
                    select(InterviewReport).where(
                        InterviewReport.interview_session_id == interview_id
                    )
                )
                assert report is not None and interview is not None
                # 보고서 commit 뒤 worker가 종료돼도 후속 전달 의도는 같은 DB에 남는다.
                await ensure_request(
                    db,
                    user_id=interview.user_id,
                    report_id=report.id,
                    report_revision=report.current_revision,
                )
            if request is not None:
                request.status, request.error_code = "succeeded", None
        return outcome
    except BaseException as error:
        if generation_request_id is not None:
            await asyncio.shield(
                generation.fail(sessions, generation_request_id, failure_code(error), attempts)
            )
        raise


def _build_payload(
    posting: JobPosting | None,
    turns: list[InterviewTurn],
    evidences: Mapping[uuid.UUID, list[tuple[str, Evidence]]],
    requirements: list[JdRequirement],
    rubrics: Mapping[str, object],
) -> dict[str, object]:
    """AI 모듈 입력. rubric 은 활성 score_criteria 의 값을 구조 해석 없이 key 별로 전달한다."""
    from app.features.report.jd_sources import jd_source_notes

    source_notes, source_limits = jd_source_notes(posting, requirements, turns)
    return {
        "score_keys": list(SCORE_KEYS),
        "rubrics": {key: rubrics[key] for key in SCORE_KEYS},
        "position": posting.position if posting else None,
        "company_name": posting.company_name if posting else None,
        "requirements": [
            {
                "id": str(r.id),
                "category": r.category,
                "text": r.text,
                **({"source_field": "job_posting.source_blocks"} if r.source_refs else {}),
            }
            for r in requirements
        ],
        "source_notes": source_notes,
        "limitations": source_limits,
        "turns": [
            {
                "turn_no": t.turn_no,
                "persona": t.persona,
                "question": t.question_text,
                # 질문했으나 답하지 않은 턴은 null로 보낸다. 미질문과 구분해 0단계로 판정한다.
                "answer": t.answer_text if t.answer_text and t.answer_text.strip() else None,
                "question_contract": t.question_contract,
                "analysis": t.analysis,
                "parent_turn_no": t.parent_turn_no,
                "jd_requirement_ids": [str(i) for i in t.jd_requirement_ids],
                "evidences": [
                    {
                        "id": str(e.id),
                        "usage": usage,
                        "repository_id": None if e.repository_id is None else str(e.repository_id),
                        "git_ref": e.git_ref,
                        "source_type": e.source_type,
                        "path": e.path,
                        "metadata_key": e.metadata_key,
                        "tool_name": e.tool_name,
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
    """ReportScore 값. 근거 turn 번호가 이 면접의 턴이 아니면 보정하지 않고 실패시킨다."""
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
    if isinstance(error, ReportRubricUnavailableError):
        return "report_rubric_unavailable"
    if isinstance(error, ReportDraftInvalidError):
        return "report_invalid"
    if isinstance(error, c.ContractError):
        # 점수를 낼 수 없는 key 가 있으면 AI 가 실패시킨다. 점수 없음 계약 전까지 알려진 실패다.
        return "report_unscorable_key" if error.field == "unscorable key" else "llm_failed"
    return "internal_error"


async def get_interview_user_id(db: AsyncSession, interview_id: uuid.UUID) -> uuid.UUID:
    """profile_summary enqueue 용 소유자 id. 면접이 사라졌으면 예외로 알린다."""
    interview = await db.get(InterviewSession, interview_id)
    if interview is None:
        raise LookupError("interview not found")
    return interview.user_id
