"""v6 감사 원문을 보존한 채 다음 Director에 canonical 분석을 복원한다."""

import json
from dataclasses import asdict
from uuid import uuid4

from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import InterviewTurn, LLMCallRecord
from app.features.interview.answer_context import load_answer_context, prior_analyses
from tests.agents.director_helpers import analysis, seed_turns


async def test_prior_analysis_restores_v6_wire_without_changing_the_audit_output(
    agent_sessions, agent_seed
):
    await seed_turns(agent_sessions, agent_seed, 2)
    raw = {
        "coverage_assessment": {
            "evaluation_status": "evaluated",
            "sufficiency": "sufficient",
            "covered_points": {"role": ["answer:0001"]},
            "missing_points": [],
            "limitations": ["기술 미확인"],
        },
        "technical_assessment": {
            "explanation": "기술적 판단 보류",
            "quote_ids": [],
            "evidence_refs": [],
            "limitations": ["코드 미확인"],
        },
        "contribution_scope": {
            "scope": "teammate",
            "quote_ids": ["answer:0001"],
            "unknown_reason": None,
        },
        "claim_checks": [],
        "verification_requests": [],
        "external_queries": [],
    }
    encoded = json.dumps(raw, ensure_ascii=False)
    async with agent_sessions.begin() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        turn.analysis = asdict(analysis())
        record = LLMCallRecord(
            id=uuid4(),
            interview_session_id=agent_seed["interview_id"],
            turn_id=turn.id,
            turn_no=1,
            task_name="answer_analysis",
            attempts=[
                asdict(
                    c.AttemptMetadata(
                        1,
                        "fixture",
                        "fixture",
                        "answer_analysis_v6@fixture",
                        "6",
                        1,
                        1,
                        1,
                        raw_output=encoded,
                    )
                )
            ],
        )
        db.add(record)
        identifier = str(turn.id)
    async with agent_sessions() as db:
        current = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=2,
            limits=c.ContextLimits(2, 0, "fixture"),
        )
        restored = await prior_analyses(db, current.context)
        assert restored[identifier].data == analysis()
        saved = await db.get(LLMCallRecord, record.id)
        assert saved.attempts[0]["raw_output"] == encoded


async def test_legacy_prior_analysis_keeps_its_existing_lenient_nested_decode(
    agent_sessions, agent_seed
):
    await seed_turns(agent_sessions, agent_seed, 2)
    raw = asdict(analysis())
    raw["technical_assessment"]["legacy_extra"] = "auxiliary"
    encoded = json.dumps(raw, ensure_ascii=False)
    async with agent_sessions.begin() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        turn.analysis = asdict(analysis())
        db.add(
            LLMCallRecord(
                id=uuid4(),
                interview_session_id=agent_seed["interview_id"],
                turn_id=turn.id,
                turn_no=1,
                task_name="answer_analysis",
                attempts=[
                    asdict(
                        c.AttemptMetadata(
                            1,
                            "fixture",
                            "fixture",
                            "answer_analysis_v5@fixture",
                            "5",
                            1,
                            1,
                            1,
                            raw_output=encoded,
                        )
                    )
                ],
            )
        )
        identifier = str(turn.id)
    async with agent_sessions() as db:
        current = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=2,
            limits=c.ContextLimits(2, 0, "fixture"),
        )
        restored = await prior_analyses(db, current.context)
        assert restored[identifier].data == analysis()
