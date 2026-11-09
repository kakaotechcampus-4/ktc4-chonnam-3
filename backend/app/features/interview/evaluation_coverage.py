"""확정된 질문에서 확보한 평가 기회만 다음 질문 배정에 반영한다."""

from devon_ai import contracts as c

_TECHNICAL: tuple[c.ScoreKeyId, ...] = (
    "project_understanding",
    "technical_reasoning",
    "problem_solving",
    "company_job_fit",
)


def plan_evaluation_targets(
    contracts: tuple[c.QuestionContract, ...],
    permitted: tuple[c.PersonaId, ...],
    *,
    has_jd: bool,
) -> tuple[c.EvaluationTarget, ...]:
    """한 중심 영역과 의사소통을 배정한다. 답변의 점수 확보를 뜻하지 않는다.

    구형 첫 질문에는 선언이 없으므로 과거 평가 범위를 추정하지 않고 기존 세션으로 유지한다.
    생성 후보와 재생 요청은 이 함수의 입력인 확정 질문 목록에 추가되지 않는다.
    """
    if contracts and not contracts[0].evaluation_keys:
        return ()
    covered = {key for contract in contracts for key in contract.evaluation_keys}
    targets: list[c.EvaluationTarget] = []
    for persona in permitted:
        if persona == "hr_manager":
            primary: c.ScoreKeyId = "contribution_clarity"
        elif persona == "tech_lead":
            primary = next(
                (
                    key
                    for key in _TECHNICAL
                    if key not in covered and (key != "company_job_fit" or has_jd)
                ),
                "technical_reasoning",
            )
        else:
            primary = (
                "company_job_fit"
                if has_jd and "company_job_fit" not in covered
                else "communication"
            )
        keys: tuple[c.ScoreKeyId, ...] = (
            (primary,) if primary == "communication" else (primary, "communication")
        )
        targets.append(c.EvaluationTarget(persona, keys))
    return tuple(targets)
