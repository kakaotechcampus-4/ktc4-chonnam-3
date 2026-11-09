"""고정 SHA 구간 캐시는 동일 파일의 여러 범위와 실제 재조회 원문을 함께 검증한다."""

import hashlib
from dataclasses import asdict

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.agents.director.tools import EvidenceScope
from app.db.models import Evidence, InterviewSession, LLMCallRecord, RepoAnalysis
from app.features.interview.repository_sources import (
    SourcePreparationError,
    collect_repository_sources,
)
from app.integrations.llm.client import CallBudget
from tests.agents.test_director_prepare import (
    PATH,
    TEXT,
    TREE,
    Transport,
    deep,
    run,
    settings,
    shallow,
)
from tests.agents.test_director_prepare import (
    ready as ready,
)


@pytest.mark.parametrize("tampered", [False, True])
async def test_segmented_cache_reuses_only_reread_matching_source(agent_sessions, ready, tampered):
    sources = [
        c.SourceDocument(PATH, "file", line, f"lines {number}-{number}", number, number)
        for number, line in enumerate(TEXT.splitlines(keepends=True), 1)
    ]
    areas = [
        dict(path=PATH, observation="확인한 원문 구간", scope=item.read_scope, limitations=[])
        for item in sources
    ]
    async with agent_sessions.begin() as db:
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        value = {**deep(ready), "notable_areas": areas}
        stored = [asdict(item) for item in sources]
        if tampered:
            for item in stored:
                item["content"] = "다른 원문\n"
        row.notable_areas = areas
        row.result = dict(
            analysis=value,
            rejected_areas=[],
            _source_snapshot=dict(
                head_sha=ready["sha"], sources=stored, reader_version="bounded-text-v2"
            ),
        )
    transport = Transport(ready)
    success = await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        evidence = list((await db.scalars(select(Evidence))).all())
        records = list((await db.scalars(select(LLMCallRecord))).all())
    if tampered:
        assert not success and evidence == []
        assert interview.last_error["code"] == "l2_cache_source_mismatch"
        assert transport.model_operations == []
    else:
        assert success, (
            interview.last_error,
            transport.model_operations,
            [(row.task_name, row.failure, row.discard_reason) for row in records],
        )
        assert {(item.start_line, item.end_line, item.snippet) for item in evidence} == {
            (1, 1, sources[0].content),
            (2, 2, sources[1].content),
        }
        assert transport.model_operations == ["plan", "review"]


async def test_partial_prefix_cannot_validate_an_entire_file_cache():
    from uuid import UUID

    seed = dict(repo_id=UUID(int=1), sha="a" * 40)
    text = "one\n" * 20
    raw = text.encode()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    transport = Transport(seed)

    async def handle(request):
        if request.url.path.endswith(f"/contents/{PATH}"):
            return httpx.Response(200, content=raw)
        response = await transport(request)
        if request.url.path.endswith(f"/git/trees/{TREE}"):
            payload = response.json()
            payload["tree"][0].update(sha=blob, size=len(raw))
            return httpx.Response(200, json=payload)
        return response

    config = settings().model_copy(
        update={"director_prepare_max_file_bytes": 30, "llm_max_input_bytes": 40}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(
            SourcePreparationError, match="repository_sources_unavailable"
        ) as caught:
            await collect_repository_sources(
                scope=EvidenceScope(
                    str(seed["repo_id"]), 123, "owner/sample", seed["sha"], frozenset()
                ),
                shallow=shallow(seed),
                prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
                settings=config,
                http_client=http,
                budget=CallBudget(),
                paths=(PATH,),
                read_scopes=((PATH, "entire file"),),
            )
    assert any("전체 파일" in note for note in caught.value.limitations)
    assert transport.model_operations == []
