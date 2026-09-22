import asyncio
import json
from dataclasses import asdict

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import agent


@pytest.fixture
def plan():
    return c.QuestionPlan(
        question_id="question-3",
        turn=3,
        contract=c.QuestionContract(
            "수정 특성 확인",
            (c.RequiredPoint("writes", "수정 특성"),),
            (),
            (),
            "수정 빈도와 변경 방식",
        ),
        allowed_personas=("tech_lead", "domain_lead"),
        remaining_candidates=2,
    )


@pytest.fixture
def personas():
    return tuple(
        c.Persona(name, ("BE 주입 질문 책임",), ("BE 주입 금지 전제",))
        for name in ("tech_lead", "hr_manager", "domain_lead")
    )


@pytest.fixture
def question(plan):
    return c.Question(
        "tech_lead", "데이터의 수정 빈도와 변경 방식은 어떤가요?", "cache", plan.contract, (), ()
    )


@pytest.fixture
def model_request():
    return c.ModelRequest(
        "director_v1",
        "fixture-model",
        "BE 주입 Director prompt",
        "fixture-p1",
        '{"type":"object"}',
        "fixture-s1",
        "{}",
        1.0,
        100,
    )


@pytest.fixture
def run_director(plan, personas, model_request):
    def run(*outputs, review=None, **kwargs):
        calls, reviews = [], []
        outcomes = iter(outputs)

        async def client(request):
            calls.append(request)
            value = next(outcomes)
            if isinstance(value, BaseException):
                raise value
            raw = value if isinstance(value, str) else json.dumps(asdict(value))
            return c.ModelResponse(raw, "actual-model")

        def reviewer(current_plan, candidate):
            reviews.append(candidate)
            if review is not None:
                return review(current_plan, candidate)
            return c.QuestionCandidateReview(current_plan, candidate, True, True, True, True, True)

        args = dict(
            request=model_request, plan=plan, personas=personas, client=client, review=reviewer
        )
        args.update(kwargs)
        return asyncio.run(agent.generate_question(**args)), calls, reviews

    return run


@pytest.fixture
def turn_record():
    def make(turn, persona="hr_manager"):
        contract = c.QuestionContract(
            f"역할 확인 {turn}", (c.RequiredPoint("role", "역할"),), (), (), "본인 역할"
        )
        question = c.Question(persona, f"역할은 무엇인가요 {turn}?", "role", contract, (), ())
        checked = c.validate_question(
            question,
            review=c.QuestionReview(question.text, contract),
            allowed_personas=(persona,),
            evidence_refs=frozenset(),
            basis_refs=frozenset(),
            jd_requirement_ids=frozenset(),
        )
        answer = c.SubmittedAnswer("answer", turn, "팀원이 구현했습니다")
        analysis = c.AnswerAnalysis(
            "evaluated",
            "sufficient",
            (c.CoveredPoint("role", (answer.text,)),),
            (),
            c.TechnicalAssessment("역할 확인", (), (), ("기술 주장 없음",)),
            "teammate",
            (answer.text,),
            (),
            False,
            (),
            (),
        )
        result = c.validate_analysis(
            analysis,
            question=checked,
            answer_text=answer.text,
            evidence_refs=frozenset(),
            allowed_locations=frozenset(),
        )
        return (
            c.QuestionReady(f"q-{turn}", turn, c.ModelSuccess(checked, ())),
            c.AnalysisHistory(checked, answer, result),
        )

    return make


@pytest.fixture
def progress_for(turn_record):
    from devon_ai.agents.director import turn_policy as policy

    def make(personas):
        progress = policy.TurnProgress()
        for turn, persona in enumerate(personas, 1):
            ready, record = turn_record(turn, persona)
            progress = policy.complete_answer(policy.record_question(progress, ready), record)
        return progress

    return make
