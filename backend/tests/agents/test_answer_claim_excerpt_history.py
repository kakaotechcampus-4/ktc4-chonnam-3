"""격리 schema에서 v7 발췌를 Director·리포트에 복원하고 최초 JSONB를 보존한다."""

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_context import load_answer_context, prior_analyses
from app.features.report.history import enrich_report_history
from app.llm_tasks.report import ReportDraftInvalidError
from tests.agents.director_helpers import analysis, seed_turns


@pytest.mark.parametrize("damaged", [None, "unknown_unit", "outside_excerpt", "wrong_schema"])
async def test_v7_claim_excerpts_restore_in_both_consumers_without_rewriting_audit(
    agent_sessions, agent_seed, damaged
):
    await seed_turns(agent_sessions, agent_seed, 3)
    answer = "TTL은 30초이고 자동 연장은 꺼져 있습니다. 다음 문장은 별도 구간입니다."
    contract = c.QuestionContract(
        "설정 설명", (c.RequiredPoint("settings", "TTL과 연장 설정"),), (), (), "제공한 설정"
    )
    initial = c.AnswerAnalysis(
        "evaluated",
        "insufficient",
        (),
        ("settings",),
        c.TechnicalAssessment("미확인", (), (), ()),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("최초 분석은 미확인이다.",),
    )
    raw = {
        "coverage_assessment": {
            "evaluation_status": "evaluated",
            "sufficiency": "sufficient",
            "covered_points": {"settings": ["answer:0001"]},
            "missing_points": [],
            "limitations": [],
        },
        "technical_assessment": {
            "explanation": "설정 설명은 관찰했고 구현 원문은 미확인이다.",
            "quote_ids": ["answer:0001"],
            "evidence_refs": [],
            "limitations": [],
        },
        "contribution_scope": {
            "scope": "unknown",
            "quote_ids": [],
            "unknown_reason": "기여 미확인",
        },
        "claim_checks": [
            {
                "quote_id": "answer:0001",
                "claim_excerpt": text,
                "status": "unverified",
                "evidence_refs": [],
                "limitations": ["원문 코드가 제공되지 않았다."],
            }
            for text in ("TTL은 30초", "자동 연장은 꺼져 있습니다.")
        ],
        "verification_requests": [],
        "external_queries": [],
    }
    if damaged == "unknown_unit":
        raw["claim_checks"][0]["quote_id"] = "fabricated"
    elif damaged == "outside_excerpt":
        raw["claim_checks"][0]["claim_excerpt"] = "다음 문장은 별도 구간입니다."
    schema = "6" if damaged == "wrong_schema" else "7"
    encoded = json.dumps(raw, ensure_ascii=False)
    async with agent_sessions.begin() as db:
        first = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        first.analysis = asdict(analysis())
        second = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 2))
        second.question_text = "현재 TTL과 연장 설정을 설명해 주세요."
        second.question_contract = asdict(contract)
        second.answer_text = answer
        second.analysis = json.loads(json.dumps(asdict(initial)))
        identifier = second.id
        record = LLMCallRecord(
            id=uuid4(),
            interview_session_id=agent_seed["interview_id"],
            turn_id=second.id,
            turn_no=2,
            task_name="answer_analysis",
            attempts=[
                asdict(
                    c.AttemptMetadata(
                        1,
                        "fixture",
                        "fixture",
                        "answer_analysis_v7@fixture",
                        schema,
                        1,
                        1,
                        1,
                        raw_output=encoded,
                    )
                )
            ],
        )
        db.add(record)
        record_id = record.id
    async with agent_sessions() as db:
        current = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=3,
            limits=c.ContextLimits(2, 0, "fixture"),
        )
        turn = await db.get(InterviewTurn, identifier)
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        payload = {
            "turns": [{"turn_no": 2, "evidences": []}],
            "requirements": [],
            "limitations": [],
        }
        if damaged:
            with pytest.raises(AgentStateError, match="analysis_contract_invalid"):
                await prior_analyses(db, current.context)
            with pytest.raises(ReportDraftInvalidError, match="history"):
                await enrich_report_history(db, interview, [turn], payload)
        else:
            restored = await prior_analyses(db, current.context)
            assert [claim.claim_text for claim in restored[str(identifier)].data.claim_checks] == [
                "TTL은 30초",
                "자동 연장은 꺼져 있습니다.",
            ]
            report = await enrich_report_history(db, interview, [turn], payload)
            assert [
                item["claim_text"] for item in report["turns"][0]["analysis"]["claim_checks"]
            ] == [
                "TTL은 30초",
                "자동 연장은 꺼져 있습니다.",
            ]
        saved = await db.get(LLMCallRecord, record_id)
        assert saved.attempts[0]["raw_output"] == encoded
        assert turn.analysis == json.loads(json.dumps(asdict(initial)))
