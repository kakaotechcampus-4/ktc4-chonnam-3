"""사적 Plan v4도 최초 실패·원문을 보존하며 자동 슬롯 하나만 쓴다."""

import json
from dataclasses import asdict
from uuid import uuid4, uuid5

import httpx
import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, PromptVersion
from tests.agents.director_helpers import analysis, approved_review, response
from tests.agents.test_auto_replan import answer, payload, seed


@pytest.mark.parametrize("kind", ["rewrite", "replan", "no_valid_candidate", "second_reject"])
async def test_v17_pg_preserves_raw_and_uses_at_most_one_auto_slot(
    agent_sessions, agent_seed, kind
):
    await seed(agent_sessions, agent_seed, "director_v17@fixture")
    async with agent_sessions.begin() as db:
        prompt = await db.scalar(select(PromptVersion).where(PromptVersion.task_name == "director"))
        prompt.template = "## 공통\n범위\n## 질문 생성\n요청\n## 독립 검토\n전체 질문 검토\n"
    sent, plans, reviews = [], [], 0
    call_id = uuid4()

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            persona = "tech_lead"
            targets = item["context"].get("evaluation_targets", [])
            keys = next((row["keys"] for row in targets if row["persona"] == persona), [])
            question = {
                "persona": persona,
                "preamble": "",
                "request": (
                    "본인의 역할을 설명해 주세요."
                    if not plans
                    else "팀과 본인의 역할을 구분해 설명해 주세요."
                ),
                "topic_code": "role",
                "question_contract": {
                    "point_key": "role",
                    "assumptions": [],
                    "basis_refs": [],
                    "evaluation_keys": keys,
                },
                "evidence_refs": [],
                "jd_requirement_ids": [],
                "question_type": "main",
                "parent_turn_id": None,
            }
            plans.append(question)
            return response(
                {"question": question, "intent": "역할 확인", "reason_summary": "허용 범위"}
            )
        reviews += 1
        review = approved_review()
        if reviews == 1 or kind == "second_reject":
            review["plan_valid" if kind == "replan" else "wording_valid"] = False
            review["safe_alternative"] = kind != "no_valid_candidate"
        review["point_coverage"] = [
            {
                "key": "role",
                "status": "asked",
                "question_excerpt": item["question"]["question_contract"]["required_points"][0][
                    "description"
                ],
            }
        ]
        return response(review)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        first = await answer(agent_sessions, agent_seed, http, call_id=call_id)
        sent_after_first = len(sent)
        replay = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert len(sent) == sent_after_first
    assert first.next_turn_id == replay.next_turn_id
    recovered = kind in {"rewrite", "replan"}
    assert (first.failure is None) is recovered
    assert len(sent) == (3 if kind == "no_valid_candidate" else 5)
    assert sum("answer" in row for row in sent) == 1
    assert len(plans) == reviews == (1 if kind == "no_valid_candidate" else 2)
    if kind != "no_valid_candidate":
        assert sent[3]["recovery_feedback"]["recovery"] == (
            "replan" if kind == "replan" else "rewrite"
        )
        assert "recovery_feedback" not in sent[4]
    async with agent_sessions() as db:
        original = await db.get(LLMCallRecord, uuid5(call_id, "director"))
        assert original.failure["error_code"] == "director_" + (
            "no_valid_candidate"
            if kind == "no_valid_candidate"
            else "candidate_replan"
            if kind == "replan"
            else "candidate_rewrite"
        )
        assert original.turn_id is None
        assert [row["schema_version"] for row in original.attempts] == [
            "director-plan.v4",
            "director-review.v3",
        ]
        raw = json.loads(original.attempts[0]["raw_output"])
        assert raw["question"] == plans[0]
        assert "purpose" not in raw["question"]["question_contract"]
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        ledger = interview.context_state.get("question_retry_v1", {})
        assert len(ledger) == int(kind != "no_valid_candidate")
        assert len(list(await db.scalars(select(InterviewTurn)))) == (2 if recovered else 1)
        original_turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        assert original_turn.answer_text == "팀원 담당입니다"
        if recovered:
            stored = await db.get(InterviewTurn, first.next_turn_id)
            assert stored.question_text == plans[1]["request"]
            assert stored.question_contract["purpose"] == plans[1]["request"]
            assert stored.question_contract["required_points"] == [
                {
                    "key": "role",
                    "description": plans[1]["request"],
                }
            ]
            entry = next(iter(ledger.values()))
            assert entry["kind"] == "auto" and entry["status"] == "succeeded"
