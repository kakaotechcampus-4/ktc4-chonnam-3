"""실제 수집·L2 검증의 미확인 범위를 Director 두 호출에 보존한다."""

import json
from uuid import uuid4

import httpx
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import InterviewSession, RepoAnalysis
from tests.agents.director_helpers import approved_review, plan, response, settings


async def test_fixed_repository_limitations_reach_director_plan_and_independent_review(
    agent_sessions,
    agent_seed,
):
    from app.features.interview.answer_context import load_answer_context
    from app.features.interview.director_service import start_director

    source_limit = "파일 원문 조회를 완료하지 못했습니다: src/unread.py: evidence_not_text"
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.context_state = {
            "preparation_repository_limitations": {
                str(agent_seed["repo_id"]): [source_limit],
                str(uuid4()): ["다른 저장소의 한계는 전달하지 않음"],
            }
        }
        for row in await db.scalars(select(RepoAnalysis)):
            if row.analysis_level == "l1":
                row.result = {"limitations": ["L1 한정 범위"]}
            else:
                row.result = {
                    "analysis": {
                        "limitations": ["L2 일부 코드만 확인"],
                        "notable_areas": [
                            {"path": "src/main.py", "limitations": ["일부 함수 범위만 확인"]}
                        ],
                    },
                    "rejected_areas": [
                        {
                            "path": "src/missing.py",
                            "stage": "semantic",
                            "reason_summary": "invalid field: unread source",
                        }
                    ],
                }
        db.add(
            RepoAnalysis(
                repository_id=agent_seed["repo_id"],
                head_sha="b" * 40,
                analysis_level="l2",
                prompt_version="other-ref",
                model="fixture",
                status="partial",
                result={"analysis": {"limitations": ["다른 SHA의 한계는 전달하지 않음"]}},
            )
        )
    received = []

    async def handle(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        received.append(payload)
        notes = payload["context"]["repositories"][0]["limitations"]
        assert source_limit in notes
        assert "L1 한정 범위" in notes and "L2 일부 코드만 확인" in notes
        assert any("src/main.py" in note and "일부 함수 범위" in note for note in notes)
        assert any("src/missing.py" in note and "unread source" in note for note in notes)
        assert all("전달하지 않음" not in note for note in notes)
        return response(plan() if payload["operation"] == "plan" else approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
    assert result.turn_id is not None and result.failure is None
    assert [payload["operation"] for payload in received] == ["plan", "review"]
    async with agent_sessions() as db:
        current = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            limits=c.ContextLimits(2, 0, "test"),
        )
    assert source_limit in current.context.repositories[0].limitations
