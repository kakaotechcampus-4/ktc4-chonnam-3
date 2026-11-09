"""전체 구조 metadata는 원문 Evidence·조회권한·Director 모델 입력과 구분해 저장한다."""

import json

import httpx
from sqlalchemy import select

from app.db.models import Evidence, InterviewSession
from app.features.interview.agent_queries import load_evidence_scope
from tests.agents.test_director_prepare import PATH, TREE, Transport, run
from tests.agents.test_director_prepare import ready as ready


async def test_inventory_is_preserved_without_expanding_evidence_or_model_context(
    agent_sessions, ready
):
    transport = Transport(ready)
    inventory_only = [f"{number:04d}-inventory-only.custom" for number in range(40)]

    async def handle(request):
        response = await transport(request)
        if request.url.path.endswith(f"/git/trees/{TREE}"):
            body = response.json()
            body["tree"].extend(
                dict(path=path, mode="100644", type="blob", sha="d" * 40) for path in inventory_only
            )
            return httpx.Response(200, json=body)
        return response

    assert await run(agent_sessions, ready, handle)
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        metadata = interview.context_state["repository_source_inventories"][str(ready["repo_id"])]
        assert metadata["head_sha"] == ready["sha"]
        assert set(metadata["paths"]) == {PATH, *inventory_only}
        assert metadata["model_candidate_paths"] == [] and metadata["limitations"] == []
        scope = await load_evidence_scope(
            db,
            user_id=ready["owner"],
            interview_id=ready["interview_id"],
            repository_id=ready["repo_id"],
        )
        assert len(scope.allowed_paths) == 16 and inventory_only[-1] not in scope.allowed_paths
        assert list(await db.scalars(select(Evidence.path))) == [PATH]
    assert transport.model_operations == ["plan", "review"]
    assert inventory_only[-1] not in json.dumps(transport.model_payloads, ensure_ascii=False)
