"""실제 서비스 AI 실행기로 9턴과 답변 재개·조회 중단을 검증한다."""

import copy
import json
from collections import Counter
from dataclasses import asdict

import pytest
from devon_ai import contracts as c
from director_cases import build_cohort, content_hash

from scripts.ai_eval_bridge import ServiceExecutor
from scripts.director_trajectory import advance, create_trajectory


class Provider:
    """외부 HTTP만 대체한다. Plan·Review·T3 계약 검증은 실제 실행한다."""

    def __init__(self, *, verify=False, external_at=None, verify_at=None, fail_at=None):
        self.requests = []
        self.verify = verify
        self.external_at = external_at
        self.verify_at = verify_at
        self.fail_at = fail_at

    async def __call__(self, request, validator):
        self.requests.append(request)
        if request.prompt.task_name == "answer_analysis":
            analysis_no = sum(item.prompt.task_name == "answer_analysis" for item in self.requests)
            text = request.payload["answer"]["text"]
            raw = {
                "evaluation_status": "evaluated",
                "sufficiency": "sufficient",
                "covered_points": [
                    {"key": point["key"], "answer_quotes": [text]}
                    for point in request.payload["question"]["question_contract"]["required_points"]
                ],
                "missing_points": [],
                "technical_assessment": {
                    "explanation": "합성 관찰",
                    "answer_quotes": [text],
                    "evidence_refs": [],
                    "limitations": ["합성 답변"],
                },
                "contribution_scope": {"scope": "unknown", "answer_quotes": []},
                "claim_checks": [],
                "needs_verification": self.verify or analysis_no == self.verify_at,
                "verification_requests": [],
                "limitations": ["합성 답변"],
                "external_queries": [],
            }
            if self.verify or analysis_no == self.verify_at:
                repo, sha, path = request.payload["allowed_locations"][0]
                raw["verification_requests"] = [
                    {
                        "claim_text": text,
                        "purpose": "구현 확인",
                        "repository_id": repo,
                        "git_ref": sha,
                        "allowed_paths": [path],
                    }
                ]
            if analysis_no == self.external_at:
                raw["needs_verification"] = True
                raw["external_queries"] = [
                    {
                        "query": "Python retry official documentation",
                        "purpose": "가정한 장애 대응 근거 확인",
                    }
                ]
        elif request.payload["operation"] == "review":
            raw = {
                "plan_valid": True,
                "context_valid": True,
                "wording_valid": True,
                "contract_matches": True,
                "safe_alternative": True,
                "reason_summary": "유효",
            }
        else:
            context = request.payload["context"]
            persona = context["allowed_personas"][0]
            target = next(
                item for item in context["evaluation_targets"] if item["persona"] == persona
            )
            jd = context["jd_requirements"][0]["id"]
            fit = "company_job_fit" in target["keys"]
            refs = [{"kind": "jd_requirement", "id": jd}] if fit else []
            question = c.Question(
                persona,
                "제공된 프로젝트의 판단 근거를 설명해 주세요.",
                "reasoning",
                c.QuestionContract(
                    "판단 근거",
                    (c.RequiredPoint("point", "판단 근거"),),
                    (),
                    tuple(c.BasisRef(item["kind"], item["id"]) for item in refs),
                    "제공한 자료에 한정한다.",
                    tuple(target["keys"]),
                ),
                (),
                (jd,) if fit else (),
            )
            raw = {
                "question": asdict(question),
                "intent": "판단 근거 확인",
                "reason_summary": "합성 계획",
            }
        raw = json.loads(json.dumps(raw, ensure_ascii=False))
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "gpt-6-luna",
            request.prompt.version,
            request.schema_version,
            1,
            10,
            10,
            raw_output=json.dumps(raw, ensure_ascii=False),
        )
        if (
            request.prompt.task_name == "answer_analysis"
            and sum(item.prompt.task_name == "answer_analysis" for item in self.requests)
            == self.fail_at
        ):
            return c.ModelResult(
                None, c.CallFailure("provider", "fixture_failed", "실패"), (attempt,)
            )
        try:
            value = validator(raw)
            return c.ModelResult(value, None, (attempt,))
        except c.ContractError as error:
            return c.ModelResult(
                None, c.CallFailure(error.stage, "fixture_invalid", "invalid"), (attempt,)
            )


def executor(provider, analysis_version="answer_analysis_v2"):
    prompts = {
        "director": c.PromptSpec("director", "director_v8", "gpt-6-luna", "template"),
        "answer_analysis": c.PromptSpec(
            "answer_analysis", analysis_version, "gpt-6-luna", "template"
        ),
    }
    return ServiceExecutor(prompts, c.CallLimits(30, 1000, 262144, 1048576), lambda: provider)


def seed():
    return create_trajectory(build_cohort().select("pilot")[0], session_id="trajectory-1")


def answer(state):
    return {
        "question_sha256": content_hash(state["turns"][-1]["question"]),
        "text": "합성 지원자의 답변이며 실제 질문에 맞춰 작성했습니다.",
        "origin": "synthetic_codex",
    }


async def test_nine_turns_use_real_analysis_and_director_without_extra_final_question():
    provider = Provider()
    service = executor(provider)
    state = await advance(seed(), service)
    for _ in range(9):
        assert state["status"] == "awaiting_answer"
        state = await advance(state, service, answer=answer(state))
    assert state["status"] == "completed"
    assert len(state["turns"]) == 9
    assert all(turn["analysis"] is not None for turn in state["turns"])
    assert Counter(turn["question"]["persona"] for turn in state["turns"]) == {
        "hr_manager": 1,
        "tech_lead": 6,
        "domain_lead": 2,
    }
    assert len(provider.requests) == 27
    assert state["scope"]["database_executed"] is False
    assert state["scope"]["tool_io_executed"] is False


async def test_pending_question_can_resume_without_generating_it_again():
    provider = Provider()
    service = executor(provider)
    pending = await advance(seed(), service)
    assert len(provider.requests) == 2
    resumed = await advance(json.loads(json.dumps(pending)), service)
    assert resumed == pending and len(provider.requests) == 2
    wrong = answer(pending) | {"question_sha256": "0" * 64}
    with pytest.raises(ValueError, match="question"):
        await advance(pending, service, answer=wrong)
    assert len(provider.requests) == 2


async def test_tool_request_stops_the_core_runner_without_claiming_lookup_completed():
    provider = Provider(verify=True)
    service = executor(provider)
    state = await advance(seed(), service)
    state = await advance(state, service, answer=answer(state))
    assert state["status"] == "requires_tools"
    assert len(state["turns"]) == 1 and len(provider.requests) == 3
    assert state["turns"][0]["analysis"]["needs_verification"] is True
    assert state["scope"]["tool_io_executed"] is False


async def test_modified_source_in_a_saved_trajectory_is_rejected_before_call():
    provider = Provider()
    state = copy.deepcopy(seed())
    state["materials"]["evidence"][0]["content"] = "변경 원문"
    with pytest.raises(ValueError, match="binding"):
        await advance(state, executor(provider))
    assert provider.requests == []


@pytest.mark.parametrize("query_kind", ["external", "repository", "analysis_failure"])
async def test_final_answer_finishes_only_after_confirmed_analysis_and_preserves_lookup_limit(
    query_kind,
):
    provider = Provider(
        external_at=9 if query_kind == "external" else None,
        verify_at=9 if query_kind == "repository" else None,
        fail_at=9 if query_kind == "analysis_failure" else None,
    )
    service = executor(provider, analysis_version="answer_analysis_v3")
    state = await advance(seed(), service)
    for _ in range(9):
        state = await advance(state, service, answer=answer(state))
    assert len(provider.requests) == 27 and len(state["turns"]) == 9
    assert state["scope"]["tool_io_executed"] is False
    if query_kind == "external":
        assert state["status"] == "completed"
        assert state["turns"][-1]["analysis"]["external_queries"]
        assert state["external_searches"][-1] == {
            "status": "insufficient_analysis",
            "source_ids": [],
            "searched_scope": [],
            "limitations": ["external_lookup_not_executed:final_turn"],
            "error_code": "final_turn_lookup_not_executed",
        }
        assert "external_lookup_not_executed:final_turn" in state["limitations"]
    elif query_kind == "repository":
        assert state["status"] == "requires_tools"
        assert state["turns"][-1]["analysis"]["verification_requests"]
    else:
        assert state["status"] == "failed" and state["turns"][-1]["analysis"] is None
