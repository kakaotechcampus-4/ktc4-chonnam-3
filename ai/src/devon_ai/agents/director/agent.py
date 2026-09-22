"""Single Director's question generation; Controller owns turns and publication."""

import json
from collections.abc import Callable
from dataclasses import asdict, replace

from devon_ai import contracts as c
from devon_ai.llm_tasks import ModelCall, call_model

type QuestionReviewer = Callable[[c.QuestionPlan, c.Question], c.QuestionCandidateReview]


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
) -> c.QuestionReady | c.QuestionRejected:
    """Generate once from a prepared plan; no automatic semantic repair or finish.

    BE supplies prompt/config, authorized reference registries and permissions.
    review must independently assess the exact candidate in the current Context;
    it must not trust self-validation fields in the generator's response.
    """
    c._convert(c.QuestionPlan, plan, "question plan", wire=False)
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
    payload = {
        "plan": asdict(plan),
        "personas": [asdict(persona) for persona in personas],
        "evidence_refs": sorted(evidence_refs),
        "basis_refs": sorted(basis_refs),
        "jd_requirement_ids": sorted(jd_requirement_ids),
    }

    def validate(candidate: c.Question) -> c.ContractChecked[c.Question]:
        if candidate.persona not in plan.allowed_personas:
            raise c.ContractError("semantic", "persona permission")
        c._references(candidate.evidence_refs, evidence_refs, "question evidence")
        c._references(candidate.question_contract.basis_refs, basis_refs, "question basis")
        c._references(candidate.jd_requirement_ids, jd_requirement_ids, "question JD")
        assessment = review(plan, candidate)
        if (
            type(assessment) is not c.QuestionCandidateReview
            or assessment.plan != plan
            or assessment.question != candidate
        ):
            raise c.ContractError("semantic", "review binding")
        if not (
            assessment.premises_valid
            and assessment.context_valid
            and assessment.wording_valid
            and assessment.contract_matches
            and candidate.question_contract == plan.contract
        ):
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
