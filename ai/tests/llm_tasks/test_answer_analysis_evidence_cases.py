"""spec/ai/features/answer-evaluation.md 필수 대조 사례 5~8. 모델 출력은 고정 fixture다.

근거 채택·도구 실패·평가 불가·후속 보완의 경계를 확인하며 실제 모델 품질은 검증하지 않는다.
"""

import pytest

from devon_ai import contracts as c

KEYS = ("read_pattern", "write_pattern", "cache_purpose")


def covered(*pairs):
    return [{"key": key, "answer_quotes": [quote]} for key, quote in pairs]


# 5. 유사하지만 무관한 코드와 버전이 다른 코드는 지지 근거로 채택하지 않는다.
CLAIM = "조회가 많아서"


def claim(**changes):
    base = {
        "claim_text": CLAIM,
        "status": "unverified",
        "evidence_refs": [],
        "limitations": ["미조회"],
    }
    return {**base, **changes}


def request(ref):
    return {
        "claim_text": CLAIM,
        "purpose": "캐시 적용 코드 확인",
        "repository_id": "repo-1",
        "git_ref": ref,
        "allowed_paths": ["cache.py"],
    }


@pytest.mark.parametrize(
    "checks",
    [
        [claim(status="supported", limitations=[])],  # 근거 없이 지지
        [
            claim(status="supported", evidence_refs=["ev-other"], limitations=[])
        ],  # 등록되지 않은 근거
    ],
)
def test_support_without_a_registered_basis_is_rejected(kit, run, checks):
    result = run(kit.Provider(kit.analysis_output(claim_checks=checks)))
    assert result.data is None and result.failure.stage == "semantic"


def test_unverified_claim_and_in_scope_request_are_kept_without_running_a_tool(kit, run):
    output = kit.analysis_output(
        claim_checks=[claim()],
        needs_verification=True,
        verification_requests=[request(kit.REF)],
    )
    allowed = frozenset({("repo-1", kit.REF, "cache.py")})
    provider = kit.Provider(output)
    result = run(provider, allowed_locations=allowed)
    assert result.data.data.verification_requests[0].git_ref == kit.REF
    assert len(provider.requests) == 1  # Tool 실행 없이 후보만 만든다.


def test_request_for_another_ref_is_rejected(kit, run):
    output = kit.analysis_output(
        claim_checks=[claim()],
        needs_verification=True,
        verification_requests=[request(kit.OTHER_REF)],
    )
    result = run(
        kit.Provider(output), allowed_locations=frozenset({("repo-1", kit.REF, "cache.py")})
    )
    assert result.data is None and result.failure.stage == "semantic"


# 6. 도구 실패를 허위 주장으로 판단하지 않는다.
def test_tool_failure_cannot_become_a_conflicting_claim(kit, run):
    failed = c.ToolResult("tool_error", (), (), ("조회 시간 초과",), "tool_timeout")
    conflicting = claim(status="conflicting", limitations=[])
    rejected = run(
        kit.Provider(kit.analysis_output(claim_checks=[conflicting])), tool_results=(failed,)
    )
    assert rejected.data is None and rejected.failure.stage == "semantic"
    provider = kit.Provider(
        kit.analysis_output(claim_checks=[claim(limitations=["도구 조회 실패"])])
    )
    kept = run(provider, tool_results=(failed,))
    assert kept.data.data.claim_checks[0].status == "unverified"
    assert provider.requests[0].payload["tool_results"][0]["status"] == "tool_error"


# 7. 평가 불가 상태와 실제 설명 부족을 구분한다.
def test_a_submitted_dont_know_is_insufficient_not_unevaluable_or_wrong(kit, run):
    output = kit.analysis_output(
        sufficiency="insufficient",
        covered_points=[],
        missing_points=list(KEYS),
        technical_assessment={
            "explanation": "설명이 없어 기술적 정확성은 판단하지 않는다.",
            "answer_quotes": [],
            "evidence_refs": [],
            "limitations": ["답변이 없어 판단 보류"],
        },
    )
    provider = kit.Provider(output)
    result = run(provider, answer="모르겠습니다.")
    assert len(provider.requests) == 1  # 정상 제출 답변은 입력 실패로 막지 않는다.
    data = result.data.data
    assert (data.evaluation_status, data.sufficiency, data.claim_checks) == (
        "evaluated",
        "insufficient",
        (),
    )


def test_unevaluable_status_keeps_the_reason_and_has_no_sufficiency(kit, run):
    unevaluable = kit.analysis_output(
        evaluation_status="not_evaluable",
        sufficiency=None,
        covered_points=[],
        missing_points=[],
        limitations=["질문 전제가 현재 자료와 맞지 않아 평가할 수 없다."],
    )
    assert run(kit.Provider(unevaluable)).data.data.sufficiency is None
    for changes in ({"sufficiency": "insufficient"}, {"limitations": []}):
        result = run(kit.Provider({**unevaluable, **changes}))
        assert result.data is None and result.failure.stage == "semantic"


# 8. 후속 보완을 최종 피드백에 연결한다. (최종 피드백 입력 구성은 이 task의 범위 밖이다.)
def test_follow_up_supplements_a_missing_point_without_changing_earlier_turns(kit, run):
    contract = c.QuestionContract(
        "수정 특성 확인", (c.RequiredPoint("write_pattern", "수정 특성"),), (), (), "보완"
    )
    first = kit.make_context()
    third = c.HistoryTurn("turn-3", "tech_lead", "캐시를 선택한 이유는?", kit.ANSWER, "analysis-3")
    context = kit.make_context(
        current_turn_id="turn-4",
        turn_no=4,
        history=first.history + (third,),
        current_question_contract=contract,
    )
    answer = "수정은 하루 한 번 배치로만 일어납니다."
    output = kit.analysis_output(
        sufficiency="sufficient",
        covered_points=covered(("write_pattern", "하루 한 번 배치로만")),
        missing_points=[],
        technical_assessment={
            "explanation": "수정 빈도 설명이 앞선 캐시 선정 이유와 모순되지 않는다.",
            "answer_quotes": ["하루 한 번 배치로만"],
            "evidence_refs": [],
            "limitations": [],
        },
    )
    provider = kit.Provider(output)
    result = run(
        provider,
        context=context,
        question=kit.checked_question(contract),
        turn_id="turn-4",
        answer=answer,
    )
    assert result.data.data.sufficiency == "sufficient"
    history = provider.requests[0].payload["history"]
    # 이전 Turn의 원문과 최초 분석 참조는 그대로 전달하며 재평가하지 않는다.
    assert history[-1] == {
        "turn_id": "turn-3",
        "question": third.question,
        "answer": kit.ANSWER,
        "analysis_ref": "analysis-3",
    }


def test_quote_from_another_turn_is_rejected_even_if_the_shape_is_valid(kit, run):
    output = kit.analysis_output(
        covered_points=covered(
            ("read_pattern", "PostgreSQL입니다"), ("cache_purpose", "DB 부하를 줄이려고")
        )
    )
    result = run(kit.Provider(output))
    assert result.data is None and result.failure.stage == "semantic"
