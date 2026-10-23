import asyncio
import importlib
import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director.agent import candidate_recovery

REF = "a" * 40
PROMPT = c.PromptSpec("director", "director_v2", "fixture-model", "template")
LIMITS = c.CallLimits(1, 512, 65536, 65536)


def runtime():
    return importlib.import_module("devon_ai.agents.director.runtime")


def context(**changes):
    return replace(
        c.Context(
            "interview-1",
            None,
            1,
            9,
            (),
            ("hr_manager",),
            (),
            (),
            (),
            None,
            (),
            (),
            c.ContextLimits(2, 0, "fixture"),
        ),
        **changes,
    )


def question():
    return c.Question(
        "hr_manager",
        "프로젝트에서 맡은 역할을 소개해 주세요.",
        "role",
        c.QuestionContract(
            "본인 역할 소개",
            (c.RequiredPoint("role", "본인이 맡은 역할"),),
            (),
            (),
            "역할",
        ),
        (),
        (),
    )


def plan(candidate=None, **changes):
    result = {
        "question": asdict(candidate or question()),
        "intent": "역할 확인",
        "reason_summary": "첫 자기소개에서 역할을 확인한다.",
    }
    result.update(changes)
    return json.loads(json.dumps(result))


def review(**changes):
    result = {
        "plan_valid": True,
        "context_valid": True,
        "wording_valid": True,
        "contract_matches": True,
        "safe_alternative": True,
        "reason_summary": "현재 원문과 목적에 맞는 한 가지 질문이다.",
    }
    result.update(changes)
    return result


class Provider:
    """외부 모델만 대체하며 입력 구성·검증·판단은 실제 Director를 실행한다."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.requests = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        output = self.outputs.pop(0)
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "fixture-model",
            "director_v2",
            request.schema_version,
            2,
            10,
            10,
        )
        if isinstance(output, c.CallFailure):
            return c.ModelResult(None, output, (attempt,))
        if isinstance(output, BaseException):
            raise output
        try:
            data = validator(output)
        except c.ContractError as exc:
            return c.ModelResult(
                None,
                c.CallFailure(exc.stage, "llm_failed", "invalid"),
                (attempt,),
            )
        return c.ModelResult(data, None, (attempt,))


def run(provider, ctx=None, **options):
    return asyncio.run(
        runtime().run_director(
            ctx or context(),
            prompt=PROMPT,
            limits=LIMITS,
            model_call=provider,
            **options,
        )
    )


def test_runtime_generates_a_plan_reviews_it_and_returns_a_checked_ask_decision():
    provider = Provider(plan(), review())
    result = run(provider)

    assert result.succeeded
    assert result.data.decision.data.next_step == "ask"
    assert result.data.decision.data.target == "본인 역할 소개"
    assert result.data.question.data == question()
    assert result.data.generation is result.attempts[0]
    assert len(result.attempts) == 2
    assert [r.max_attempts for r in provider.requests] == [1, 1]
    assert [r.schema_version for r in provider.requests] == [
        "director-plan.v1",
        "director-review.v1",
    ]
    assert [r.payload["operation"] for r in provider.requests] == ["plan", "review"]
    assert provider.requests[1].payload["question"] == asdict(question())


@pytest.mark.parametrize("remaining", [0, 1])
def test_runtime_reserves_a_second_attempt_before_generating_any_candidate(remaining):
    provider = Provider(plan(), review())
    result = run(provider, context(limits=c.ContextLimits(remaining, 0, "fixture")))
    assert result.failure.stage == "budget"
    assert result.attempts == ()
    assert provider.requests == []


@pytest.mark.parametrize(
    "assessment,recovery",
    [
        (review(plan_valid=False, reason_summary="구현과 기여를 사실로 오인했다."), "replan"),
        (review(context_valid=False, reason_summary="이미 확인한 목적의 반복이다."), "replan"),
        (review(wording_valid=False, reason_summary="별개 질문 세 개가 섞였다."), "rewrite"),
        (review(contract_matches=False), "rewrite"),
        (review(plan_valid=False, safe_alternative=False), "no_valid_candidate"),
    ],
)
def test_independent_review_classifies_failures_without_rewriting_or_another_call(
    assessment,
    recovery,
):
    candidate = question()
    if not assessment["plan_valid"]:
        candidate = replace(
            candidate,
            text="직접 구현한 캐시에서 성능을 50% 개선한 방법을 설명해 주세요.",
            question_contract=replace(
                candidate.question_contract,
                assumptions=("지원자가 캐시를 직접 구현했고 성능을 50% 개선했다.",),
            ),
        )
    elif not assessment["wording_valid"]:
        candidate = replace(
            candidate, text="역할을 소개하고 설계 이유와 성능 수치와 협업 갈등도 설명해 주세요."
        )
    elif not assessment["contract_matches"]:
        candidate = replace(candidate, text="캐시 무효화의 일반 원리를 설명해 주세요.")
    provider = Provider(plan(candidate), assessment)
    ctx = later_context() if not assessment["context_valid"] else context()
    result = run(provider, ctx)
    assert result.data is None
    assert result.failure.stage == "semantic"
    assert candidate_recovery(result.failure).recovery == recovery
    assert len(result.attempts) == 2
    assert len(provider.requests) == 2
    assert "self_review" not in provider.requests[1].payload


@pytest.mark.parametrize("where", ["plan", "review"])
def test_schema_failures_stop_without_an_extra_attempt(where):
    bad_plan = plan()
    bad_plan["question"]["question_contract"]["required_points"] = []
    provider = Provider(bad_plan) if where == "plan" else Provider(plan(), review(plan_valid="yes"))
    result = run(provider)
    assert result.failure.stage == "schema"
    assert result.data is None
    assert len(result.attempts) == (1 if where == "plan" else 2)


@pytest.mark.parametrize("field", ["persona", "evidence", "jd", "basis"])
def test_runtime_rejects_unallowed_persona_and_unregistered_references_before_review(field):
    output = plan()
    candidate = output["question"]
    if field == "persona":
        candidate["persona"] = "tech_lead"
    elif field == "basis":
        candidate["question_contract"]["basis_refs"] = [{"kind": "evidence", "id": "invented"}]
    else:
        candidate["evidence_refs" if field == "evidence" else "jd_requirement_ids"] = ["invented"]
    provider = Provider(output)
    result = run(provider)
    assert result.failure.stage == "semantic"
    assert len(result.attempts) == 1


def test_first_hr_policy_rejects_stale_history_without_a_model_call():
    provider = Provider(plan(), review())
    result = run(
        provider, context(history=(c.HistoryTurn("old", "hr_manager", "질문", "답", None),))
    )
    assert result.failure.error_code == "director_input_invalid"
    assert provider.requests == []


def checked_analysis(*, contribution="teammate", supported=False, needs=True):
    q = question()
    checked = c.validate_question(
        q,
        review=c.QuestionReview(q.text, q.question_contract),
        allowed_personas=("hr_manager",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    analysis = c.AnswerAnalysis(
        "evaluated",
        "sufficient",
        (c.CoveredPoint("role", ("팀원이 캐시를 구현했습니다.",)),),
        (),
        c.TechnicalAssessment("구현 역할을 정정했다.", (), (), ()),
        c.ContributionScope(contribution, ("팀원이 캐시를 구현했습니다.",)),
        (
            c.ClaimCheck(
                "캐시를 구현했습니다",
                "supported" if supported else "unverified",
                ("ev-1",) if supported else (),
                () if supported else ("코드를 확인하지 않았다.",),
            ),
        ),
        needs,
        (
            c.VerificationRequest(
                "캐시를 구현했습니다",
                "현재 주장과 실제 구현의 비교",
                "repo-1",
                REF,
                ("cache.py",),
            ),
        )
        if needs
        else (),
        (),
    )
    return c.validate_analysis(
        analysis,
        question=checked,
        answer_text="팀원이 캐시를 구현했습니다.",
        evidence_refs=frozenset({"ev-1"}),
        allowed_locations=frozenset({("repo-1", REF, "cache.py")}),
    )
