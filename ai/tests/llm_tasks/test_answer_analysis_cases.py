"""spec/ai/features/answer-evaluation.md의 필수 대조 사례. 모델 출력은 고정 fixture다.

실제 모델이 이런 출력을 내는지는 검증하지 않는다. 여기서는 같은 출력이 계약·의미 검증을
통과하거나 거절되는 경계만 확인한다.
"""

from dataclasses import asdict

import pytest

FULL = "조회가 많고 수정은 하루 한 번뿐이라 DB 부하를 줄이려고 캐시했습니다."
KEYS = ("read_pattern", "write_pattern", "cache_purpose")
NO_QUOTES = {
    "explanation": "인용할 설명이 없어 기술적 정확성은 판단하지 않는다.",
    "answer_quotes": [],
    "evidence_refs": [],
    "limitations": ["설명 부족"],
}


def covered(*pairs):
    return [{"key": key, "answer_quotes": [quote]} for key, quote in pairs]


# 1. 같은 질문에 충분·부분·불충분 답변을 넣으면 Contract에 맞는 차이가 나타난다.
@pytest.mark.parametrize(
    "answer,changes,expected",
    [
        (
            FULL,
            {
                "sufficiency": "sufficient",
                "covered_points": covered(
                    ("read_pattern", "조회가 많고"),
                    ("write_pattern", "수정은 하루 한 번뿐이라"),
                    ("cache_purpose", "DB 부하를 줄이려고"),
                ),
                "missing_points": [],
            },
            ("sufficient", 3, ()),
        ),
        (None, {}, ("partial", 2, ("write_pattern",))),
        (
            "잘 모르겠지만 캐시를 썼습니다.",
            {
                "sufficiency": "insufficient",
                "covered_points": [],
                "missing_points": list(KEYS),
                "technical_assessment": NO_QUOTES,
            },
            ("insufficient", 0, KEYS),
        ),
    ],
)
def test_sufficient_partial_and_insufficient_follow_the_question_contract(
    kit, run, answer, changes, expected
):
    result = run(kit.Provider(kit.analysis_output(**changes)), answer=answer or kit.ANSWER)
    data = result.data.data
    assert (data.sufficiency, len(data.covered_points), data.missing_points) == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"sufficiency": "sufficient"},  # 부족 항목이 남았는데 충분
        {"sufficiency": "partial", "missing_points": []},
        {"sufficiency": "insufficient", "covered_points": [], "missing_points": []},
    ],
)
def test_sufficiency_that_contradicts_the_points_is_a_semantic_failure(kit, run, changes):
    result = run(kit.Provider(kit.analysis_output(**changes)))
    assert result.data is None and result.failure.stage == "semantic"


# 2. 길고 틀린 답변과 짧고 맞는 답변을 별도 축으로 판단한다.
def test_sufficiency_and_technical_assessment_are_independent_axes(kit, run):
    long_wrong = kit.analysis_output(
        sufficiency="sufficient",
        covered_points=covered(
            ("read_pattern", "조회가 많고"),
            ("write_pattern", "수정은 하루 한 번뿐이라"),
            ("cache_purpose", "DB 부하를 줄이려고"),
        ),
        missing_points=[],
        technical_assessment={
            "explanation": "필수 항목은 모두 설명했지만 캐시가 항상 최신이라는 전제는 부정확하다.",
            "answer_quotes": ["DB 부하를 줄이려고 캐시했습니다"],
            "evidence_refs": [],
            "limitations": [],
        },
    )
    short_right = kit.analysis_output()
    long_result = run(kit.Provider(long_wrong), answer=FULL).data.data
    short_result = run(kit.Provider(short_right)).data.data
    assert long_result.sufficiency == "sufficient"
    assert "부정확" in long_result.technical_assessment.explanation
    assert short_result.sufficiency == "partial"
    assert "타당" in short_result.technical_assessment.explanation


# 3. 질문하지 않은 항목은 missing_points에 넣지 않는다.
@pytest.mark.parametrize("field", ["missing_points", "covered_points"])
def test_a_point_the_question_did_not_ask_for_is_rejected(kit, run, field):
    output = kit.analysis_output()
    if field == "missing_points":
        output[field] = ["write_pattern", "ttl"]
    else:
        output[field] = covered(("ttl", "캐시했습니다"))
    result = run(kit.Provider(output))
    assert result.data is None and result.failure.stage == "semantic"


# 4. 팀원 구현을 본인 경험으로 가정하지 않고 정정을 반영한다.
def test_teammate_attribution_is_kept_and_prior_records_are_untouched(kit, run):
    answer = "저는 설계만 했고 캐시 구현은 팀원이 했습니다. " + kit.ANSWER
    scope = {"scope": "teammate", "answer_quotes": ["캐시 구현은 팀원이 했습니다"]}
    context = kit.make_context()
    before = asdict(context)
    result = run(
        kit.Provider(kit.analysis_output(contribution_scope=scope)), context=context, answer=answer
    )
    assert result.data.data.contribution_scope.scope == "teammate"
    assert asdict(context) == before  # 과거 답변 원문과 이력은 덮어쓰지 않는다.


@pytest.mark.parametrize(
    "scope",
    [
        {"scope": "self", "answer_quotes": []},
        {"scope": "self", "answer_quotes": ["제가 직접 구현했습니다"]},  # 답변에 없는 인용
    ],
)
def test_self_contribution_requires_a_quote_from_the_submitted_answer(kit, run, scope):
    answer = "캐시 구현은 팀원이 했습니다. " + kit.ANSWER
    result = run(kit.Provider(kit.analysis_output(contribution_scope=scope)), answer=answer)
    assert result.data is None and result.failure.stage == "semantic"
