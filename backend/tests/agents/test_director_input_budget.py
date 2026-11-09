"""원문·8개 이력·기여 정정을 보존하고 Plan/Review 실제 전송 예산을 지킨다."""

import json
from dataclasses import asdict

import httpx
import pytest
from devon_ai import contracts as c
from devon_ai.agents.director import runtime

from app.agents.director.runtime_adapter import execute_director
from app.core.config import Settings
from app.integrations.llm.client import CallBudget, request_size
from tests.agents.director_helpers import response


def fixture():
    ref = "a" * 40
    contract = c.QuestionContract(
        "역할 확인", (c.RequiredPoint("role", "본인 역할"),), (), (), "역할"
    )
    question = c.Question("tech_lead", "본인 역할을 설명해 주세요.", "role", contract, (), ())
    checked_question = c.validate_question(
        question,
        review=c.QuestionReview(question.text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    history, previous = [], {}
    personas = ["hr_manager", *(["tech_lead"] * 5), "domain_lead", "domain_lead"]
    for n in range(1, 9):
        answer = "제가 캐시를 구현했습니다." if n < 8 else "정정합니다. 팀원이 캐시를 구현했습니다."
        history.append(
            c.HistoryTurn(
                f"turn-{n}", personas[n - 1], f"{n}번째 본인 역할 질문", answer, f"analysis-{n}"
            )
        )
        analysis = c.AnswerAnalysis(
            "evaluated",
            "sufficient",
            (c.CoveredPoint("role", (answer,)),),
            (),
            c.TechnicalAssessment("역할 발언을 확인했다.", (), (), ("구현은 미확인",)),
            c.ContributionScope("self" if n < 8 else "teammate", (answer,)),
            (),
            False,
            (),
            (),
        )
        previous[f"turn-{n}"] = c.validate_analysis(
            analysis,
            question=checked_question,
            answer_text=answer,
            evidence_refs=frozenset(),
            allowed_locations=frozenset(),
        )
    content = "actual original code line\n" * 1000
    evidence = tuple(
        c.Evidence(
            f"e-{n}",
            "repo",
            ref,
            "file",
            f"module{n}/source.custom",
            None,
            content,
            None,
            "원문 관찰",
            1,
            1000,
        )
        for n in range(5)
    )
    context = c.Context(
        "interview",
        "turn-8",
        9,
        9,
        (
            c.PersonaCount("hr_manager", 1),
            c.PersonaCount("tech_lead", 5),
            c.PersonaCount("domain_lead", 2),
        ),
        ("tech_lead",),
        (c.JDRequirement("jd", "백엔드 역할 설명", "required", "requirements", ()),),
        (c.ContextRepository("repo", ref, True, (), ()),),
        tuple(history),
        contract,
        evidence,
        (),
        c.ContextLimits(2, 0, "test"),
    )
    return context, previous


@pytest.mark.parametrize("invented", [False, True])
async def test_ninth_question_preserves_sources_and_roles_inside_two_gateway_attempts(invented):
    context, previous = fixture()
    refs = (c.BasisRef("evidence", "invented" if invented else "e-0"),)
    contract = c.QuestionContract(
        "코드 이해 확인", (c.RequiredPoint("code", "코드 설명"),), (), refs, "코드 이해"
    )
    question = c.Question(
        "tech_lead", "원문 코드를 설명해 주세요.", "code", contract, (refs[0].id,), ()
    )
    sent = []

    def handle(request):
        sent.append(request.content)
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        if payload["operation"] == "plan":
            return response(
                dict(question=asdict(question), intent="코드 이해", reason_summary="관찰 범위 확인")
            )
        return response(
            dict(
                plan_valid=True,
                context_valid=True,
                wording_valid=True,
                contract_matches=True,
                safe_alternative=True,
                reason_summary="원문에 맞음",
            )
        )

    llm = Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=65536,
    ).require_llm()
    budget = CallBudget()
    prompt = c.PromptSpec("director", "director_v2", "fixture", "원문과 이력으로 질문")
    payload, sources = runtime._input_payload(
        context,
        prompt,
        llm.call_limits("director"),
        previous["turn-8"],
        {c.BasisRef("job_posting", "job"): "실제 공고 원문"},
        previous,
        (),
    )
    measured = c.ModelRequest(
        prompt,
        {**payload, "operation": "plan"},
        "DirectorPlan",
        "director-plan.v1",
        runtime._plan_schema(False),
        llm.call_limits("director"),
        max_attempts=1,
    )
    assert len(sources) == 15  # 코드5·JD1·답변8·공고1을 서버에서 모두 검증한다.
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await execute_director(
            context,
            prompt=prompt,
            settings=llm,
            budget=budget,
            answer_analysis=previous["turn-8"],
            prior_analyses=previous,
            reference_texts={c.BasisRef("job_posting", "job"): "실제 공고 원문"},
            http_client=http,
        )
    if invented:
        assert result.failure.stage == "semantic" and len(sent) == 1
    else:
        assert result.succeeded and len(sent) == 2 and budget.remaining_attempts == 0
    assert len(sent[0]) == request_size(measured)
    for raw in sent:
        assert len(raw) <= 262144
        payload = json.loads(json.loads(raw)["input"][0]["content"][0]["text"])
        assert payload["context"] == json.loads(json.dumps(asdict(context)))
        assert len(payload["prior_analyses"]) == 8
        assert payload["prior_analyses"]["turn-1"]["contribution_scope"]["scope"] == "self"
        assert payload["answer_analysis"]["contribution_scope"]["scope"] == "teammate"
        assert payload["reference_texts"] == [
            {"kind": "job_posting", "id": "job", "text": "실제 공고 원문"}
        ]
