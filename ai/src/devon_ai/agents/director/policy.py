"""모델 호출 없이 후속 질문의 범위와 남은 평가 기회를 제한한다."""

from dataclasses import replace
from functools import cache
from typing import Literal

from devon_ai import contracts as c

_AREAS: tuple[c.ScoreKeyId, ...] = (
    "project_understanding",
    "technical_reasoning",
    "problem_solving",
    "company_job_fit",
    "contribution_clarity",
    "communication",
)
_BITS = {key: 1 << index for index, key in enumerate(_AREAS)}
# 고정 서비스 배분이며 BE 설정도 다른 값은 거절한다.
_QUOTA: dict[c.PersonaId, int] = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}


def can_cover(
    uncovered: frozenset[c.ScoreKeyId],
    remaining_slots: tuple[int, int, int],
    *,
    has_jd: bool,
) -> bool:
    """기술·도메인·HR 남은 슬롯으로 적용 가능한 영역을 모두 질문할 수 있는지 검사한다."""
    if any(type(count) is not int or count < 0 for count in remaining_slots):
        return False
    if "company_job_fit" in uncovered and not has_jd:
        return False
    choices = (
        tuple(
            _BITS[key] | _BITS["communication"]
            for key in _AREAS[:4]
            if key != "company_job_fit" or has_jd
        ),
        (
            (_BITS["company_job_fit"] | _BITS["communication"], _BITS["communication"])
            if has_jd
            else (_BITS["communication"],)
        ),
        (_BITS["contribution_clarity"] | _BITS["communication"],),
    )

    @cache
    def search(mask: int, technical: int, domain: int, hr: int) -> bool:
        if mask == 0:
            return True
        slots = (technical, domain, hr)
        index = next((index for index, count in enumerate(slots) if count), None)
        if index is None:
            return False
        reduced = list(slots)
        reduced[index] -= 1
        return any(search(mask & ~choice, *reduced) for choice in choices[index])

    return search(sum(_BITS[key] for key in uncovered), *remaining_slots)


def with_follow_up_options(
    context: c.Context,
    analysis: c.ContractChecked[c.AnswerAnalysis] | None,
) -> c.Context:
    """검증된 직전 답변만 재대조한다. 과거 입력의 옵션이나 분석 실패를 승인으로 쓰지 않는다."""
    clean = replace(context, follow_up_options=())
    contract = context.current_question_contract
    parents = tuple(turn for turn in context.history if turn.turn_id == context.current_turn_id)
    if (
        not context.presented_evaluation_keys
        or not context.evaluation_targets
        or contract is None
        or not contract.evaluation_keys
        or type(analysis) is not c.ContractChecked
        or type(analysis.data) is not c.AnswerAnalysis
        or len(parents) != 1
        or not context.history
        or parents[0] != context.history[-1]
        or parents[0].persona not in context.allowed_personas
        or not set(contract.evaluation_keys).issubset(context.presented_evaluation_keys)
    ):
        return clean
    counts = {item.persona: item.count for item in context.persona_counts}
    if (
        set(counts) != set(_QUOTA)
        or sum(counts.values()) != context.turn_no - 1
        or len(context.history) != context.turn_no - 1
        or any(
            sum(turn.persona == key for turn in context.history) != value
            for key, value in counts.items()
        )
    ):
        return clean
    parent = parents[0]
    try:
        # ContractChecked도 다른 턴에서 왔을 수 있으므로 현재 계약과 실제 인용을 다시 검증한다.
        rebound = c.validate_analysis_for_contract(
            analysis.data,
            contract=contract,
            answer_text=parent.answer,
            evidence_refs=frozenset(
                item.evidence_id for item in context.evidence if item.evidence_id
            ),
            allowed_locations=frozenset(
                (item.repository_id, item.git_ref, item.path)
                for item in context.evidence
                if item.path is not None
                and item.repository_id is not None
                and item.git_ref is not None
            ),
        ).data
    except c.ContractError:
        return clean
    if rebound.needs_verification:
        return clean
    covered = {point.key for point in rebound.covered_points}
    intent: Literal["complete", "clarify"]
    if rebound.evaluation_status == "needs_clarification":
        intent = "clarify"
        points = tuple(
            point.key
            for point in contract.required_points
            if point.key not in covered or point.key in rebound.missing_points
        )
    elif rebound.evaluation_status == "evaluated" and rebound.sufficiency == "partial":
        intent = "complete"
        points = tuple(
            point.key for point in contract.required_points if point.key in rebound.missing_points
        )
    else:
        # 충분한 답변의 자동 심화와 정상적인 '모름'의 반복은 이 정책에서 강제하지 않는다.
        return clean
    if not points:
        return clean
    remaining = (
        _QUOTA["tech_lead"] - counts["tech_lead"] - int(parent.persona == "tech_lead"),
        _QUOTA["domain_lead"] - counts["domain_lead"] - int(parent.persona == "domain_lead"),
        _QUOTA["hr_manager"] - counts["hr_manager"] - int(parent.persona == "hr_manager"),
    )
    required = frozenset(
        key for key in _AREAS if key != "company_job_fit" or context.jd_requirements
    )
    if not can_cover(
        required - frozenset(context.presented_evaluation_keys),
        remaining,
        has_jd=bool(context.jd_requirements),
    ):
        return clean
    option = c.FollowUpOption(
        parent.persona, parent.turn_id, contract.evaluation_keys, points, intent
    )
    return replace(clean, follow_up_options=(option,))


def validate_question_policy(question: c.Question, context: c.Context) -> None:
    """v9 후보가 Controller의 새 질문 배정 또는 정확한 후속 선택지에 속해야 한다."""
    if not context.evaluation_targets:
        return
    keys = question.question_contract.evaluation_keys
    if question.question_type == "main":
        expected = {target.persona: target.keys for target in context.evaluation_targets}
        if question.persona not in expected or keys != expected[question.persona]:
            raise c.ContractError("semantic", "evaluation targets")
        return
    points = {point.key for point in question.question_contract.required_points}
    if not any(
        option.persona == question.persona
        and option.parent_turn_id == question.parent_turn_id
        and option.evaluation_keys == keys
        and points.issubset(option.missing_point_keys)
        for option in context.follow_up_options
    ):
        raise c.ContractError("semantic", "follow up option")
