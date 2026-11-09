"""기본 공통 필드를 가진 #213에서도 구형 공개 실행 함수가 동작하는지 검사한다."""

import asyncio
import json
from dataclasses import asdict

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import runtime
from devon_ai.llm_tasks import answer_analysis

LIMITS = c.CallLimits(1, 512, 65536, 65536)


def contract():
    return c.QuestionContract("역할 설명", (c.RequiredPoint("role", "역할 설명"),), (), (), "역할")


def question():
    return c.Question("hr_manager", "역할을 설명해 주세요.", "role", contract(), (), ())


def context(answering=False):
    return c.Context(
        "i",
        "turn-1" if answering else None,
        1,
        9,
        (),
        ("hr_manager",),
        (),
        (),
        (),
        contract() if answering else None,
        (),
        (),
        c.ContextLimits(2, 0, "fixture"),
    )


def legacy_plan(optional=False):
    raw = json.loads(json.dumps(asdict(question())))
    if not optional:
        raw.pop("question_type")
        raw.pop("parent_turn_id")
        raw["question_contract"].pop("evaluation_keys")
    return {"question": raw, "intent": "역할", "reason_summary": "역할 확인"}


REVIEW = {
    key: True
    for key in (
        "plan_valid",
        "context_valid",
        "wording_valid",
        "contract_matches",
        "safe_alternative",
    )
}
REVIEW["reason_summary"] = "질문과 계약 일치"


class Provider:
    def __init__(self, *outputs):
        self.outputs, self.requests = list(outputs), []

    async def __call__(self, request, validator):
        self.requests.append(request)
        output = self.outputs.pop(0)
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "fixture",
            request.prompt.version,
            request.schema_version,
            1,
            None,
            None,
        )
        try:
            data = validator(output)
        except c.ContractError as exc:
            return c.ModelResult(
                None, c.CallFailure(exc.stage, "llm_failed", "fixture"), (attempt,)
            )
        return c.ModelResult(data, None, (attempt,))


def run_director(provider, version="director_v2"):
    return asyncio.run(
        runtime.run_director(
            context(),
            prompt=c.PromptSpec("director", version, "fixture", "fixture"),
            limits=LIMITS,
            model_call=provider,
        )
    )


@pytest.mark.parametrize("optional", [False, True])
def test_legacy_director_omitted_or_empty_common_defaults_keep_plan_review_budget(optional):
    provider = Provider(legacy_plan(optional), REVIEW)
    result = run_director(provider)
    assert result.succeeded and result.data.question.data == question()
    assert len(provider.requests) == 2
    assert all(request.max_attempts == 1 for request in provider.requests)


@pytest.mark.parametrize("corrupt", ["extra", "missing", "nested_extra"])
def test_director_still_rejects_extra_or_missing_required_fields(corrupt):
    raw = legacy_plan(True)
    if corrupt == "extra":
        raw["question"]["approve"] = True
    elif corrupt == "missing":
        raw["question"].pop("text")
    else:
        raw["question"]["question_contract"]["approve"] = True
    provider = Provider(raw, REVIEW)
    result = run_director(provider)
    assert not result.succeeded and len(provider.requests) == 1


def analysis(optional=False):
    raw = {
        "evaluation_status": "evaluated",
        "sufficiency": "sufficient",
        "covered_points": [{"key": "role", "answer_quotes": ["팀원 역할입니다"]}],
        "missing_points": [],
        "technical_assessment": {
            "explanation": "역할을 설명했다",
            "answer_quotes": [],
            "evidence_refs": [],
            "limitations": [],
        },
        "contribution_scope": {"scope": "unknown", "answer_quotes": []},
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": ["개인 기여는 확인하지 않았다"],
    }
    if optional:
        raw["external_queries"] = []
    return raw


def run_analysis(provider, version="answer_analysis_v1"):
    q = question()
    checked = c.validate_question(
        q,
        review=c.QuestionReview(q.text, q.question_contract),
        allowed_personas=("hr_manager",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    return asyncio.run(
        answer_analysis.analyze_answer(
            context(True),
            checked,
            turn_id="turn-1",
            answer_text="팀원 역할입니다",
            prompt=c.PromptSpec("answer_analysis", version, "fixture", "fixture"),
            limits=LIMITS,
            model_call=provider,
        )
    )


@pytest.mark.parametrize("optional", [False, True])
def test_legacy_analysis_allows_omitted_or_empty_external_default(optional):
    provider = Provider(analysis(optional))
    result = run_analysis(provider)
    assert result.succeeded and result.data.data.external_queries == ()
    assert len(provider.requests) == 1


def test_legacy_analysis_does_not_claim_new_external_query_capability():
    raw = analysis(True)
    raw["needs_verification"] = True
    raw["external_queries"] = [{"query": "Redis TTL", "purpose": "fixture"}]
    result = run_analysis(Provider(raw))
    assert not result.succeeded


@pytest.mark.parametrize("version", ["future-fixture-version", "director_v999@deployment"])
def test_unregistered_runtime_version_never_reaches_the_provider(version):
    provider = Provider(legacy_plan(), REVIEW)
    result = run_director(provider, version)
    assert result.failure is not None
    assert result.failure.error_code == "director_input_invalid"
    assert result.attempts == () and provider.requests == []


def test_score_turn_preserves_legacy_sixth_positional_linked_requirements():
    linked = c.LinkedRequirement("jd-1", "API 개발", "required")
    turn = c.ScoreTurn("turn-1", "hr_manager", "질문", "답변", contract(), (linked,))
    assert turn.jd_requirements == (linked,)
    assert turn.jd_requirement_ids == ()
