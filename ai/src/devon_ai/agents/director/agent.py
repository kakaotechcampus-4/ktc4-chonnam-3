"""Single Director's question generation; Controller owns turns and publication."""

import json
from collections.abc import Callable
from dataclasses import asdict, replace

from devon_ai import contracts as c
from devon_ai.agents.director import turn_policy
from devon_ai.llm_tasks import ModelCall, call_model
from devon_ai.llm_tasks.answer_analysis import _current_evidence, _history_payload

type QuestionReviewer = Callable[[c.QuestionPlan, c.Question], c.QuestionCandidateReview]


def _recovery(
    plan: c.QuestionPlan,
    candidate: c.Question,
    assessment: c.QuestionCandidateReview,
) -> c.CandidateRecovery | None:
    result: c.CandidateRecovery | None
    if not assessment.premises_valid:
        result = c.CandidateRecovery("replan", "거짓 또는 유효하지 않은 전제 재계획")
    elif not assessment.context_valid:
        result = c.CandidateRecovery("replan", "현재 맥락 또는 이미 확인한 목적 재계획")
    else:
        # 표현 오류만 있으면 재작성하되, 마지막 Contract 검사에서 의미 변경을 우선 차단한다.
        result = (
            c.CandidateRecovery("rewrite", "목적과 필수 확인내용을 유지한 표현 재작성")
            if not assessment.wording_valid
            else None
        )
        if not assessment.contract_matches or candidate.question_contract != plan.contract:
            result = c.CandidateRecovery("replan", "실제 질문과 사전 목적·확인내용 불일치")
    if result is not None and (not assessment.safe_alternative or plan.remaining_candidates <= 1):
        return c.CandidateRecovery(
            "no_valid_candidate", "허용 범위 또는 남은 상한 내 유효 후보 없음"
        )
    return result


async def generate_question(
    request: c.ModelRequest,
    *,
    plan: c.QuestionPlan,
    personas: tuple[c.Persona, ...],
    client: ModelCall,
    review: QuestionReviewer,
    evidence_refs: frozenset[str] = frozenset(),
    basis_refs: frozenset[str] = frozenset(),
    jd_requirement_ids: frozenset[str] = frozenset(),
    evidence: tuple[c.AnalysisEvidence, ...] = (),
    tool_results: tuple[c.AnalysisToolResult, ...] = (),
    allowed_locations: frozenset[tuple[str, str, str]] = frozenset(),
    reference_texts: tuple[c.ReferenceText, ...] = (),
    history: tuple[c.AnalysisHistory, ...] = (),
    progress: turn_policy.TurnProgress | None = None,
) -> c.QuestionReady | c.QuestionRejected:
    """Generate once from a prepared plan; no automatic semantic repair or finish.

    BE supplies prompt/config, authorized reference registries and permissions.
    review must independently assess the exact candidate in the current Context;
    it must not trust self-validation fields in the generator's response.
    """
    c._convert(c.QuestionPlan, plan, "question plan", wire=False)
    if progress is not None:
        expected = turn_policy.plan_question(
            progress,
            plan.question_id,
            plan.contract,
            remaining_candidates=plan.remaining_candidates,
        )
        if plan.turn != expected.turn or not set(plan.allowed_personas).issubset(
            expected.allowed_personas
        ):
            raise c.ContractError("semantic", "plan turn policy")
        if history and history != progress.history:
            raise c.ContractError("semantic", "progress history mismatch")
        history = progress.history
    c.validate_personas(personas)
    c._references((), evidence_refs, "evidence registry")
    c._references(plan.contract.basis_refs, basis_refs, "planned basis")
    c._references((), jd_requirement_ids, "JD registry")
    if request.task_name != "director_v1":
        raise c.ContractError("schema", "Director task")
    recovery = c.CandidateRecovery("no_valid_candidate", "유효한 질문 후보 없음")
    if not plan.allowed_personas or plan.remaining_candidates == 0:
        return c.QuestionRejected(
            plan.question_id, c.ModelFailed(c.ModelFailure("semantic"), ()), recovery
        )
    selected = _current_evidence(evidence, tool_results, evidence_refs, allowed_locations)
    c._convert(tuple[c.ReferenceText, ...], reference_texts, "reference text", wire=False)
    source_ids = tuple(source.reference_id for source in reference_texts)
    c._unique(source_ids, "reference text identity")
    evidence_content = {item.evidence_id: item.content for item in selected}
    if any(
        source.reference_id in evidence_content
        and source.content != evidence_content[source.reference_id]
        for source in reference_texts
    ):
        raise c.ContractError("semantic", "conflicting source identity")
    c._references(tuple(jd_requirement_ids), frozenset(source_ids), "JD source required")
    c._references(tuple(basis_refs), frozenset(source_ids) | evidence_refs, "basis source required")
    _history_payload(history, plan.turn)
    payload = {
        "plan": asdict(plan),
        "personas": [asdict(persona) for persona in personas],
        "evidence_refs": sorted(evidence_refs),
        "basis_refs": sorted(basis_refs),
        "jd_requirement_ids": sorted(jd_requirement_ids),
        "reference_texts": [
            asdict(source)
            for source in reference_texts
            if source.reference_id in basis_refs | jd_requirement_ids
        ],
        "evidence": [asdict(item) for item in selected],
        "tool_results": [
            {
                **asdict(result),
                "items": [
                    asdict(item) for item in result.items if item.evidence_id in evidence_refs
                ],
            }
            for result in tool_results
        ],
        "history": [
            {
                "question": asdict(item.question.data),
                "answer": asdict(item.answer),
                "analysis": asdict(item.analysis.data),
            }
            for item in history
        ],
    }
    if progress is not None:
        payload["turn_policy"] = {
            "question_count": progress.question_count,
            "completed_count": progress.completed_count,
            "persona_counts": {
                persona: sum(item.question.data.persona == persona for item in progress.questions)
                for persona in turn_policy.PERSONAS
            },
            "tech_target": 6,
        }

    def validate(candidate: c.Question) -> c.ContractChecked[c.Question]:
        nonlocal recovery
        if candidate.persona not in plan.allowed_personas:
            raise c.ContractError("semantic", "persona permission")
        c._references(candidate.evidence_refs, evidence_refs, "question evidence")
        c._references(candidate.question_contract.basis_refs, basis_refs, "question basis")
        c._references(candidate.jd_requirement_ids, jd_requirement_ids, "question JD")
        try:
            assessment = review(plan, candidate)
        except c.ContractError:
            # 검토 연결 오류는 모델 JSON 오류가 아니므로 생성 재시도로 복구하지 않는다.
            raise c.ContractError("semantic", "independent review failed") from None
        if (
            type(assessment) is not c.QuestionCandidateReview
            or assessment.plan != plan
            or assessment.question != candidate
        ):
            raise c.ContractError("semantic", "review binding")
        rejected = _recovery(plan, candidate, assessment)
        if rejected is not None:
            recovery = rejected
            raise c.ContractError("semantic", "question assessment")
        return c.validate_question(
            candidate,
            review=c.QuestionReview(candidate.text, plan.contract),
            allowed_personas=plan.allowed_personas,
            evidence_refs=evidence_refs,
            basis_refs=basis_refs,
            jd_requirement_ids=jd_requirement_ids,
        )

    result = await call_model(
        replace(request, input_json=json.dumps(payload, ensure_ascii=False)),
        client=client,
        contract_type=c.Question,
        validate=validate,
    )
    if isinstance(result, c.ModelFailed):
        return c.QuestionRejected(plan.question_id, result, recovery)
    return c.QuestionReady(plan.question_id, plan.turn, result)
