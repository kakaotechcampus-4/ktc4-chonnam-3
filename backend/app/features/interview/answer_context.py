"""현재 답변 분석과 다음 질문의 Context 단계를 분리한다."""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast
from uuid import UUID

from devon_ai import contracts as c
from devon_ai.agents.director.agent import _references
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession, InterviewTurn, JobPosting, LLMCallRecord
from app.features.interview.agent_context import AgentStateError
from app.features.interview.agent_queries import load_evidence_scope


def restored_question(
    turn: InterviewTurn,
    context: c.Context,
    *,
    source_texts: Mapping[c.BasisRef, str] | None = None,
) -> c.ContractChecked[c.Question]:
    """원래 저장한 질문 기준만 복원하고 평가 기준을 소급 생성하지 않는다."""
    try:
        contract = c.decode(c.QuestionContract, turn.question_contract)
        question = c.Question(
            cast(c.PersonaId, turn.persona),
            turn.question_text,
            turn.topic_code or "",
            contract,
            tuple(ref.id for ref in contract.basis_refs if ref.kind == "evidence"),
            tuple(str(value) for value in turn.jd_requirement_ids),
        )
        # 저장한 계약도 현재 고정 SHA와 실제 등록 원문에 대조한다. 본인 답변은 질문 근거가 아니다.
        sources = _references(
            replace(context, history=context.history[: turn.turn_no - 1]),
            source_texts or {},
        )
        return c.validate_question(
            question,
            review=c.QuestionReview(question.text, contract),
            allowed_personas=(question.persona,),
            evidence_refs=frozenset(ref.id for ref in sources if ref.kind == "evidence"),
            basis_refs=frozenset(sources),
            jd_requirement_ids=frozenset(item.id for item in context.jd_requirements),
        )
    except c.ContractError:
        raise AgentStateError("question_contract_invalid") from None


async def reference_texts(db: AsyncSession, interview_id: UUID) -> dict[c.BasisRef, str]:
    """면접에 고정한 공고 본문만 원문 근거로 전달한다."""
    posting = await db.scalar(
        select(JobPosting)
        .join(
            InterviewSession,
            InterviewSession.job_posting_id == JobPosting.id,
        )
        .where(InterviewSession.id == interview_id)
    )
    if posting is None:
        return {}
    if not posting.raw_payload:
        return {}
    text = json.dumps(posting.raw_payload, ensure_ascii=False)
    return {c.BasisRef("job_posting", str(posting.id)): text}


async def prior_analyses(
    db: AsyncSession, context: c.Context
) -> dict[str, c.ContractChecked[c.AnswerAnalysis]]:
    """과거 최초 분석은 당시 질문·답변과 다시 맞춘 뒤 전달한다."""
    result: dict[str, c.ContractChecked[c.AnswerAnalysis]] = {}
    ids = [UUID(turn.turn_id) for turn in context.history]
    if not ids:
        return result
    interview = await db.get(InterviewSession, UUID(context.interview_id))
    if interview is None:
        raise AgentStateError("interview_unavailable")
    scopes = [
        await load_evidence_scope(
            db,
            user_id=interview.user_id,
            interview_id=interview.id,
            repository_id=UUID(repo.repository_id),
        )
        for repo in context.repositories
    ]
    locations = frozenset(
        (scope.repository_id, scope.git_ref, path)
        for scope in scopes
        for path in scope.allowed_paths
    )
    sources = await reference_texts(db, interview.id)
    for turn in await db.scalars(select(InterviewTurn).where(InterviewTurn.id.in_(ids))):
        if turn.analysis is None or not turn.answer_text:
            continue
        try:
            candidate = c.decode(c.AnswerAnalysis, turn.analysis)
            question = restored_question(turn, context, source_texts=sources)

            def validate(
                value: c.AnswerAnalysis,
                *,
                question: c.ContractChecked[c.Question] = question,
                answer_text: str = turn.answer_text,
            ) -> c.ContractChecked[c.AnswerAnalysis]:
                return c.validate_analysis(
                    value,
                    question=question,
                    answer_text=answer_text,
                    evidence_refs=frozenset(
                        item.evidence_id for item in context.evidence if item.evidence_id
                    ),
                    allowed_locations=locations,
                )

            checked = validate(candidate)
            records = await db.scalars(
                select(LLMCallRecord)
                .where(
                    LLMCallRecord.turn_id == turn.id,
                    LLMCallRecord.task_name == "answer_analysis",
                    LLMCallRecord.interview_session_id == interview.id,
                )
                .order_by(LLMCallRecord.created_at, LLMCallRecord.id)
            )
            for record in records:
                for attempt in record.attempts:
                    raw = attempt.get("raw_output")
                    if attempt.get("error_stage") is None and isinstance(raw, str):
                        # 최초 JSONB를 수정하지 않고 성공한 보강 분석을 당시 원문에 다시 대조한다.
                        checked = validate(c.decode(c.AnswerAnalysis, json.loads(raw)))
            result[str(turn.id)] = checked
        except (c.ContractError, ValueError, TypeError):
            raise AgentStateError("analysis_contract_invalid") from None
    return result
