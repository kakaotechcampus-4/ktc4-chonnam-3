"""기여 정정 사례. 모델 출력은 고정 fixture이며 기존 계약·task 동작만 확인한다.

정정이 어느 이전 Turn을 가리키는지의 연결 형식, 이전 분석의 Director 전달, 최종 피드백 입력
구성은 이 파일이 검증하지 않는다. 사용자 입력 복구·재평가는 AI-L09 합의 전까지 구현하지 않는다.
"""

import asyncio
import json
from dataclasses import FrozenInstanceError, asdict

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import agent as director

CORRECTION = "저는 설계만 했고 캐시 구현은 팀원이 했습니다."
TEAMMATE = {"scope": "teammate", "answer_quotes": ["캐시 구현은 팀원이 했습니다"]}
NO_QUOTES = {
    "explanation": "구현 설명이 없어 기술적 정확성은 판단하지 않는다.",
    "answer_quotes": [],
    "evidence_refs": [],
    "limitations": ["구현 설명 없음"],
}


def role_contract():
    return c.QuestionContract(
        "본인 역할 확인", (c.RequiredPoint("role", "본인이 맡은 역할"),), (), (), "역할 소개"
    )


def direct_impl_contract():
    # 사용자가 캐시를 직접 구현했다는 전제를 가진 질문이다.
    return c.QuestionContract(
        "직접 구현한 캐시 로직 확인",
        (c.RequiredPoint("cache_impl", "직접 구현한 캐시 로직"),),
        ("사용자가 캐시를 직접 구현했다",),
        (),
        "캐시 구현 설명",
    )


def correction_output(**changes):
    base = {
        "evaluation_status": "evaluated",
        "sufficiency": "sufficient",
        "covered_points": [{"key": "role", "answer_quotes": ["저는 설계만 했고"]}],
        "missing_points": [],
        "technical_assessment": NO_QUOTES,
        "contribution_scope": TEAMMATE,
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": ["구현 품질은 평가하지 않았다."],
    }
    return {**base, **changes}


def role_run(kit, run, output, contract=None, **options):
    contract = contract or role_contract()
    context = kit.make_context(current_question_contract=contract)
    return run(
        kit.Provider(output),
        context=context,
        question=kit.checked_question(contract),
        answer=CORRECTION,
        **options,
    )


def test_correction_to_a_role_question_confirms_the_role_and_records_the_teammate(kit, run):
    data = role_run(kit, run, correction_output()).data.data
    # 역할을 물은 질문이므로 역할 정보가 확인된 것이며 정정은 기여 범위에 남는다.
    assert (data.sufficiency, data.missing_points) == ("sufficient", ())
    assert data.covered_points[0].key == "role"
    assert (data.contribution_scope.scope, data.contribution_scope.answer_quotes) == (
        "teammate",
        ("캐시 구현은 팀원이 했습니다",),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"covered_points": [], "missing_points": []},  # 요구한 항목을 설명하지 않았는데 충분
        {  # 질문이 요구하지 않은 key로 충분을 만들 수 없다
            "covered_points": [{"key": "role", "answer_quotes": ["저는 설계만 했고"]}]
        },
    ],
)
def test_correction_never_turns_an_unrelated_question_sufficient(kit, run, changes):
    # 같은 정정 답변이라도 질문이 요구한 항목(조회·수정·선정 목적)을 설명하지 않으면 충분일 수 없다.
    output = correction_output(**changes)
    result = run(kit.Provider(output), answer=CORRECTION)
    assert result.data is None and result.failure.stage == "semantic"


def test_the_same_correction_is_insufficient_when_the_question_asked_something_else(kit, run):
    output = correction_output(
        sufficiency="insufficient",
        covered_points=[],
        missing_points=["read_pattern", "write_pattern", "cache_purpose"],
    )
    data = run(kit.Provider(output), answer=CORRECTION).data.data
    assert data.sufficiency == "insufficient" and data.contribution_scope.scope == "teammate"


def test_wrong_direct_implementation_premise_is_clarification_not_a_skill_gap(kit, run):
    output = correction_output(
        evaluation_status="needs_clarification",
        sufficiency=None,
        covered_points=[],
        limitations=["질문의 직접 구현 전제가 답변의 기여 정정과 맞지 않아 평가하지 않는다."],
    )
    result = role_run(kit, run, output, direct_impl_contract())
    data = result.data.data
    assert (data.evaluation_status, data.sufficiency, data.missing_points) == (
        "needs_clarification",
        None,
        (),
    )
    assert data.contribution_scope.scope == "teammate"
    # 평가 가능 여부를 밝히지 않은 채 상태만 바꾼 결과는 거절한다.
    no_reason = role_run(kit, run, {**output, "limitations": []}, direct_impl_contract())
    assert no_reason.data is None and no_reason.failure.stage == "semantic"


def test_correction_does_not_overwrite_earlier_answer_or_first_analysis(kit, run):
    first_text = "제가 직접 구현했습니다. 조회가 많아서 DB 부하를 줄이려고 캐시했습니다."
    first = c.validate_analysis(
        c.decode(
            c.AnswerAnalysis,
            kit.analysis_output(
                contribution_scope={"scope": "self", "answer_quotes": ["제가 직접 구현했습니다"]}
            ),
        ),
        question=kit.checked_question(),
        answer_text=first_text,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )
    history = kit.make_context().history + (
        c.HistoryTurn("turn-3", "tech_lead", "캐시를 선택한 이유는?", first_text, "analysis-3"),
    )
    contract = role_contract()
    context = kit.make_context(
        current_turn_id="turn-4",
        turn_no=4,
        history=history,
        current_question_contract=contract,
    )
    before = (asdict(context), c.to_data(first))
    provider = kit.Provider(correction_output())
    result = run(
        provider,
        context=context,
        question=kit.checked_question(contract),
        turn_id="turn-4",
        answer=CORRECTION,
    )
    # 정정은 새 분석으로만 남고 과거 원문·최초 분석은 그대로이며 같은 값으로 전달된다.
    assert result.data.data.contribution_scope.scope == "teammate"
    assert (asdict(context), c.to_data(first)) == before
    assert provider.requests[0].payload["history"][-1]["answer"] == first_text
    assert first.data.contribution_scope.scope == "self"
    with pytest.raises(FrozenInstanceError):
        first.data.contribution_scope = result.data.data.contribution_scope


def test_correction_analysis_reaches_the_next_question_input_unchanged(kit, run):
    context = kit.make_context(current_question_contract=role_contract())
    checked = role_run(kit, run, correction_output()).data
    answered = context.history + (
        c.HistoryTurn("turn-3", "tech_lead", "맡은 역할은?", CORRECTION, "analysis-3"),
    )
    next_contract = c.QuestionContract(
        "본인 담당 범위 확인", (c.RequiredPoint("scope", "본인 담당 범위"),), (), (), "범위"
    )
    next_context = kit.make_context(
        current_turn_id=None, turn_no=4, history=answered, current_question_contract=None
    )
    question = c.Question(
        "tech_lead", "맡으신 설계 범위를 설명해 주세요.", "scope", next_contract, (), ()
    )
    raw = {k: v for k, v in asdict(question).items() if k != "question_contract"}
    provider = kit.Provider(raw)

    async def review(request, candidate):
        return c.QuestionReview(candidate.text, next_contract)

    prompt = c.PromptSpec("director", "director_v1", "fixture-model", "draft")
    limits = c.CallLimits(1, 512, 65536, 65536)
    result = asyncio.run(
        director.generate_question(
            next_context,
            next_contract,
            prompt=prompt,
            limits=limits,
            model_call=provider,
            review=review,
            answer_analysis=checked,
        )
    )
    assert result.succeeded
    payload = json.loads(json.dumps(provider.requests[0].payload))
    assert payload["answer_analysis"] == c.to_data(checked)
    assert payload["answer_analysis"]["contribution_scope"]["scope"] == "teammate"
    assert payload["context"]["history"][-1]["answer"] == CORRECTION


def test_resubmitting_an_answered_turn_is_rejected_until_recovery_is_agreed(kit, run):
    # 사용자 입력 복구·재제출·재평가(AI-L09)는 구현하지 않았다. 현재는 이력에 있는 Turn을 거절한다.
    history = kit.make_context().history
    context = kit.make_context(
        history=history + (history[0].__class__("turn-3", "tech_lead", "질문", "원래 답변", None),)
    )
    provider = kit.Provider(correction_output())
    result = run(provider, context=context, answer=CORRECTION)
    assert result.failure.error_code == "answer_analysis_input_invalid"
    assert provider.requests == []
