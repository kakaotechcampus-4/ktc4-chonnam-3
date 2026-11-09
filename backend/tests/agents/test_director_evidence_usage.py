"""한 Evidence가 같은 턴의 질문 근거와 평가 근거로 함께 연결되는지 확인한다(task-08)."""

import json
from dataclasses import asdict, replace
from uuid import uuid4

import httpx
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import Evidence, InterviewTurn, TurnEvidence
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    contract,
    response,
    seed_turns,
    settings,
)


async def test_one_evidence_is_both_question_and_evaluation_basis_of_a_turn(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer, start_director

    await seed_turns(agent_sessions, agent_seed, 0)
    evidence_id = uuid4()
    async with agent_sessions.begin() as db:
        db.add(
            Evidence(
                id=evidence_id,
                interview_session_id=agent_seed["interview_id"],
                repository_id=agent_seed["repo_id"],
                git_ref=agent_seed["sha"],
                source_type="file",
                path="src/main.py",
                snippet="def main(): ...",
                tool_name=None,
                start_line=1,
                end_line=1,
            )
        )
    ref = str(evidence_id)
    # 질문 근거는 질문 계약의 basis_refs에도 evidence로 있어야 한다.
    grounded = replace(contract(), basis_refs=(c.BasisRef("evidence", ref),))
    answer = replace(
        analysis(), technical_assessment=c.TechnicalAssessment("원문과 대조", (), (ref,), ())
    )

    async def handle(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        if "answer" in payload:
            return response(asdict(answer))
        if payload["operation"] == "review":
            return response(approved_review())
        persona = payload["context"]["allowed_personas"][0]
        question = c.Question(persona, "본인의 역할을 설명해 주세요.", "role", grounded, (ref,), ())
        return response(
            {"question": asdict(question), "intent": "역할 확인", "reason_summary": "원문 기반"}
        )

    options = dict(
        user_id=agent_seed["owner"], interview_id=agent_seed["interview_id"], settings=settings()
    )

    async def links(turn_no):
        async with agent_sessions() as db:
            turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == turn_no))
            rows = await db.scalars(select(TurnEvidence).where(TurnEvidence.turn_id == turn.id))
            return {(row.evidence_id, row.usage) for row in rows}

    both = {(evidence_id, "question_basis"), (evidence_id, "evaluation_basis")}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        first = await start_director(agent_sessions, call_id=uuid4(), http_client=http, **options)
        assert first.turn_id is not None
        for turn_no in (1, 2):
            result = await process_answer(
                agent_sessions,
                turn_no=turn_no,
                text="팀원 담당입니다",
                call_id=uuid4(),
                http_client=http,
                **options,
            )
            assert result.failure is None
            # 같은 근거가 질문을 만든 근거이자 답변 평가의 근거가 될 수 있다(contracts.md usage).
            assert await links(turn_no) == both
    # 평가 근거는 답한 턴에만 붙고, 다음 턴을 처리해도 앞 턴의 연결은 바뀌지 않는다.
    assert await links(1) == both
