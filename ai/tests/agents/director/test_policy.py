from dataclasses import asdict, replace
from importlib import import_module

import pytest

from devon_ai import contracts as c


def policy():
    return import_module("devon_ai.agents.director.policy")


def contract(*keys):
    return c.QuestionContract(
        "설계의 선택 근거 확인",
        (c.RequiredPoint("approach", "선택한 방법"), c.RequiredPoint("reason", "선택 이유")),
        (),
        (),
        "제출한 답변에서 설명한 선택",
        keys,
    )


def checked_analysis(asked=None, answer="큐를 사용했습니다.", **changes):
    asked = asked or contract("project_understanding", "communication")
    question = c.Question(
        "tech_lead", "처리 방법과 선택 이유를 설명해 주세요.", "flow", asked, (), ()
    )
    checked_question = c.validate_question(
        question,
        review=c.QuestionReview(question.text, asked),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    candidate = c.AnswerAnalysis(
        "evaluated",
        "partial",
        (c.CoveredPoint("approach", (answer,)),),
        ("reason",),
        c.TechnicalAssessment("방법은 설명했으나 선택 이유는 미확인", (answer,), (), ()),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("개인 기여 미확인",),
    )
    return c.validate_analysis(
        replace(candidate, **changes),
        question=checked_question,
        answer_text=answer,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )


def context(**changes):
    asked = contract("project_understanding", "communication")
    return replace(
        c.Context(
            "session",
            "tech-1",
            3,
            9,
            (
                c.PersonaCount("hr_manager", 1),
                c.PersonaCount("tech_lead", 1),
                c.PersonaCount("domain_lead", 0),
            ),
            ("tech_lead", "domain_lead"),
            (c.JDRequirement("jd-1", "API 설계", "required", "jd_requirements.text", ()),),
            (),
            (
                c.HistoryTurn("hr-1", "hr_manager", "역할은?", "팀 작업입니다.", None),
                c.HistoryTurn(
                    "tech-1",
                    "tech_lead",
                    "처리 방법과 선택 이유를 설명해 주세요.",
                    "큐를 사용했습니다.",
                    "tech-1",
                ),
            ),
            asked,
            (),
            (),
            c.ContextLimits(2, 0, "fixture"),
            evaluation_targets=(
                c.EvaluationTarget("tech_lead", ("technical_reasoning", "communication")),
            ),
            presented_evaluation_keys=(
                "contribution_clarity",
                "communication",
                "project_understanding",
            ),
        ),
        **changes,
    )


def test_partial_answer_can_continue_previous_target_without_mutating_stored_context():
    ctx = context()
    before = asdict(ctx)
    expanded = policy().with_follow_up_options(ctx, checked_analysis())
    assert expanded.follow_up_options == (
        c.FollowUpOption(
            "tech_lead",
            "tech-1",
            ("project_understanding", "communication"),
            ("reason",),
            "complete",
        ),
    )
    assert asdict(ctx) == before
    assert expanded.evaluation_targets == ctx.evaluation_targets


def test_sufficient_or_dont_know_answer_does_not_force_a_follow_up():
    sufficient = checked_analysis(
        sufficiency="sufficient",
        missing_points=(),
        covered_points=(
            c.CoveredPoint("approach", ("큐를 사용했습니다.",)),
            c.CoveredPoint("reason", ("큐를 사용했습니다.",)),
        ),
    )
    unknown = checked_analysis(
        answer="모르겠습니다.",
        sufficiency="insufficient",
        covered_points=(),
        missing_points=("approach", "reason"),
    )
    assert policy().with_follow_up_options(context(), sufficient).follow_up_options == ()
    assert (
        policy()
        .with_follow_up_options(
            context(
                history=context().history[:-1]
                + (replace(context().history[-1], answer="모르겠습니다."),)
            ),
            unknown,
        )
        .follow_up_options
        == ()
    )


def test_analysis_is_rebound_to_actual_parent_answer_before_options_are_authorized():
    ctx = context(
        history=context().history[:-1]
        + (replace(context().history[-1], answer="아직 설명하지 않았습니다."),)
    )
    assert policy().with_follow_up_options(ctx, checked_analysis()).follow_up_options == ()


def test_legacy_or_missing_analysis_cannot_acquire_new_options():
    assert policy().with_follow_up_options(context(), None).follow_up_options == ()
    assert (
        policy()
        .with_follow_up_options(context(presented_evaluation_keys=()), checked_analysis())
        .follow_up_options
        == ()
    )


def test_clarification_preserves_unknown_status_instead_of_marking_it_a_failure():
    analysis = checked_analysis(
        evaluation_status="needs_clarification",
        sufficiency=None,
        covered_points=(),
        missing_points=(),
    )
    expanded = policy().with_follow_up_options(context(), analysis)
    assert expanded.follow_up_options[0].intent == "clarify"
    assert expanded.follow_up_options[0].missing_point_keys == ("approach", "reason")
    assert analysis.data.evaluation_status == "needs_clarification"


def test_follow_up_is_rejected_when_remaining_slots_cannot_cover_unasked_areas():
    previous = context().history
    history = (
        previous[0],
        *(replace(previous[1], turn_id=f"previous-tech-{index}") for index in range(4)),
        c.HistoryTurn("domain-1", "domain_lead", "직무는?", "경험을 연결했습니다.", None),
        previous[1],
    )
    ctx = context(
        turn_no=8,
        history=history,
        persona_counts=(
            c.PersonaCount("hr_manager", 1),
            c.PersonaCount("tech_lead", 5),
            c.PersonaCount("domain_lead", 1),
        ),
    )
    assert policy().with_follow_up_options(ctx, checked_analysis()).follow_up_options == ()


def test_pending_verification_and_not_evaluable_analysis_cannot_authorize_follow_ups():
    pending = checked_analysis(
        needs_verification=True,
        external_queries=(c.ExternalQueryRequest("HTTP retry semantics", "일반 규약 확인"),),
    )
    not_evaluable = checked_analysis(
        evaluation_status="not_evaluable",
        sufficiency=None,
        covered_points=(),
        missing_points=(),
    )
    assert policy().with_follow_up_options(context(), pending).follow_up_options == ()
    assert policy().with_follow_up_options(context(), not_evaluable).follow_up_options == ()


def test_contract_changed_since_analysis_does_not_keep_old_missing_point_permission():
    ctx = context(
        current_question_contract=c.QuestionContract(
            "다른 질문",
            (c.RequiredPoint("different", "다른 확인 대상"),),
            (),
            (),
            "다른 범위",
            ("project_understanding", "communication"),
        )
    )
    assert policy().with_follow_up_options(ctx, checked_analysis()).follow_up_options == ()


def test_options_are_not_inherited_from_an_older_context_when_analysis_is_missing():
    allowed = policy().with_follow_up_options(context(), checked_analysis())
    assert allowed.follow_up_options
    assert policy().with_follow_up_options(allowed, None).follow_up_options == ()


def test_candidate_must_match_authorized_parent_target_and_missing_point():
    ctx = policy().with_follow_up_options(context(), checked_analysis())
    follow_up = c.Question(
        "tech_lead",
        "큐를 선택한 이유는 무엇인가요?",
        "flow",
        replace(
            ctx.current_question_contract, required_points=(c.RequiredPoint("reason", "선택 이유"),)
        ),
        (),
        (),
        "follow_up",
        "tech-1",
    )
    policy().validate_question_policy(follow_up, ctx)
    for candidate in (
        replace(follow_up, parent_turn_id="hr-1"),
        replace(follow_up, persona="domain_lead"),
        replace(follow_up, question_contract=contract("problem_solving", "communication")),
        replace(
            follow_up,
            question_contract=replace(
                follow_up.question_contract,
                required_points=(c.RequiredPoint("unasked", "묻지 않은 항목"),),
            ),
        ),
    ):
        with pytest.raises(c.ContractError):
            policy().validate_question_policy(candidate, ctx)


def test_main_question_still_requires_the_existing_evaluation_target():
    ctx = policy().with_follow_up_options(context(), checked_analysis())
    candidate = c.Question(
        "tech_lead",
        "선택의 근거는?",
        "choice",
        contract("technical_reasoning", "communication"),
        (),
        (),
    )
    policy().validate_question_policy(candidate, ctx)
    with pytest.raises(c.ContractError):
        policy().validate_question_policy(
            replace(
                candidate, question_contract=contract("project_understanding", "communication")
            ),
            ctx,
        )


@pytest.mark.parametrize(
    "uncovered,slots,has_jd,want",
    [
        (("technical_reasoning", "problem_solving"), (1, 1, 0), True, False),
        (("technical_reasoning", "problem_solving"), (2, 0, 0), True, True),
        (("company_job_fit",), (0, 1, 0), True, True),
        (("company_job_fit",), (1, 0, 0), False, False),
        (("contribution_clarity",), (1, 2, 0), True, False),
        (("contribution_clarity", "communication"), (0, 0, 1), True, True),
        (("communication",), (0, 1, 0), False, True),
        ((), (0, 0, 0), False, True),
        ((), (-1, 0, 0), True, False),
    ],
)
def test_remaining_persona_capacity_respects_applicable_areas(uncovered, slots, has_jd, want):
    assert policy().can_cover(frozenset(uncovered), slots, has_jd=has_jd) is want
