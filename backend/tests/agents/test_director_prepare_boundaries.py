"""면접 준비의 고정 SHA 대조, primary 범위, run partial, L2 준비 성공 기준과
캐시 재사용 조건(task-05)을 실제 PostgreSQL로 확인한다."""

import asyncio
from dataclasses import asdict, replace
from uuid import UUID, uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import func, select, update

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    Evidence,
    InterviewSession,
    InterviewTurn,
    RepoAnalysis,
    SessionRepository,
)
from app.db.models import Repository as RepositoryRow
from tests.agents.test_director_prepare import (
    BLOB,
    PATH,
    TREE,
    Transport,
    area,
    deep,
    prepare,
    run,
    settings,
    shallow,
)
from tests.agents.test_director_prepare import ready as ready

SAMPLE = "owner/sample"


class Repositories:
    """여러 저장소의 GitHub 요청을 기본 fixture 응답으로 돌려주고 요청한 저장소를 기록한다."""

    def __init__(self, transport, ids):
        self.transport, self.ids, self.requested = transport, ids, set()

    async def __call__(self, request):
        if request.method == "POST":
            return await self.transport(request)
        for full_name, github_id in self.ids.items():
            prefix = f"/repos/{full_name}"
            if request.url.path != prefix and not request.url.path.startswith(prefix + "/"):
                continue
            self.requested.add(full_name)
            if request.url.path == prefix:
                return httpx.Response(200, json=dict(id=github_id, private=False))
            path = f"/repos/{SAMPLE}" + request.url.path.removeprefix(prefix)
            return await self.transport(httpx.Request("GET", request.url.copy_with(path=path)))
        raise AssertionError(f"예상하지 않은 GitHub 경로: {request.url.path}")


async def add_repository(sessions, seed, order, *, cached):
    """같은 run에 L1이 연결된 저장소를 order 위치로 선택한다. cached면 유효한 L2 캐시를 둔다."""
    repo_id, name = uuid4(), f"repo{order}"
    async with sessions.begin() as db:
        interview = await db.get(InterviewSession, seed["interview_id"])
        db.add(
            RepositoryRow(
                id=repo_id,
                user_id=seed["owner"],
                github_repo_id=1000 + order,
                name=name,
                full_name=f"owner/{name}",
                head_sha=seed["sha"],
            )
        )
        await db.flush()
        db.add(
            SessionRepository(
                interview_session_id=seed["interview_id"],
                repository_id=repo_id,
                snapshot_head_sha=seed["sha"],
                is_primary=False,
                display_order=order,
            )
        )
        l1 = RepoAnalysis(
            repository_id=repo_id,
            analysis_level="l1",
            head_sha=seed["sha"],
            prompt_version="fixture",
            model="fixture",
            status="succeeded",
            result=asdict(shallow({**seed, "repo_id": repo_id})),
        )
        db.add(l1)
        await db.flush()
        db.add(
            AnalysisRepoCandidate(
                analysis_job_id=interview.analysis_job_id,
                repository_id=repo_id,
                base_rank=order + 1,
                batch_no=1,
                batch_rank=order + 1,
                filter_status="eligible",
                ranking_signals={
                    "analysis": dict(
                        analysis_id=str(l1.id),
                        status="succeeded",
                        head_sha=l1.head_sha,
                        prompt_version=l1.prompt_version,
                    )
                },
            )
        )
        if cached:
            db.add(
                RepoAnalysis(
                    repository_id=repo_id,
                    analysis_level="l2",
                    head_sha=seed["sha"],
                    prompt_version="repo_deep_v1",
                    model="fixture",
                    status="succeeded",
                    notable_areas=[area()],
                    result=dict(analysis=deep({**seed, "repo_id": repo_id}), rejected_areas=[]),
                )
            )
    return repo_id, f"owner/{name}", 1000 + order


async def failure(sessions, seed):
    async with sessions() as db:
        interview = await db.get(InterviewSession, seed["interview_id"])
        assert interview.status == "preparing_failed"
        return interview.last_error["code"]


@pytest.mark.parametrize("stale", ["session_snapshot", "l1_result"])
async def test_changed_fixed_sha_stops_before_external_io(agent_sessions, ready, stale):
    async with agent_sessions.begin() as db:
        if stale == "session_snapshot":
            # 면접에 고정된 SHA와 run의 L1 분석 SHA가 다르면 다른 ref를 섞지 않는다.
            await db.execute(update(SessionRepository).values(snapshot_head_sha="d" * 40))
        else:
            l1 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l1"))
            l1.result = asdict(replace(shallow(ready), head_sha="d" * 40))
    transport = Transport(ready)
    assert not await run(agent_sessions, ready, transport)
    expected = "repository_snapshot_changed" if stale == "session_snapshot" else "bound_l1_invalid"
    assert await failure(agent_sessions, ready) == expected
    assert transport.github == [] and transport.model_operations == []
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0


async def test_source_collection_rejects_l1_from_another_snapshot_without_github():
    from app.agents.director.tools import EvidenceScope
    from app.features.interview.repository_sources import (
        SourcePreparationError,
        collect_repository_sources,
    )
    from app.integrations.llm.client import CallBudget
    from tests.agents.test_director_prepare import settings

    seed = dict(repo_id=UUID(int=1), sha="a" * 40)
    transport = Transport(seed)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        with pytest.raises(SourcePreparationError) as error:
            await collect_repository_sources(
                scope=EvidenceScope(str(seed["repo_id"]), 123, SAMPLE, seed["sha"], frozenset()),
                shallow=replace(shallow(seed), head_sha="d" * 40),
                prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
                settings=settings(),
                http_client=http,
                budget=CallBudget(),
            )
    assert error.value.code == "l1_snapshot_mismatch"
    assert transport.github == [] and transport.model_operations == []


async def test_only_first_two_selected_repositories_become_primary(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(SessionRepository)
            .where(SessionRepository.repository_id == ready["repo_id"])
            .values(display_order=0)
        )
    second = await add_repository(agent_sessions, ready, 1, cached=True)
    third = await add_repository(agent_sessions, ready, 2, cached=False)
    transport = Repositories(
        Transport(ready), {SAMPLE: 123, second[1]: second[2], third[1]: third[2]}
    )
    assert await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        rows = {row.repository_id: row for row in await db.scalars(select(SessionRepository))}
        assert [rows[key].is_primary for key in (ready["repo_id"], second[0], third[0])] == [
            True,
            True,
            False,
        ]
        # 선택에서 빠지지 않고 고정 SHA는 남지만 L2 원문 조회와 분석 대상에서는 제외한다.
        assert rows[third[0]].snapshot_head_sha == ready["sha"]
        third_l2 = await db.scalar(
            select(RepoAnalysis).where(
                RepoAnalysis.repository_id == third[0], RepoAnalysis.analysis_level == "l2"
            )
        )
        assert third_l2 is None
    assert transport.requested == {SAMPLE, second[1]}
    assert transport.transport.model_operations == ["plan", "review"]


@pytest.mark.parametrize("status", ["partial", "failed"])
async def test_partial_run_can_prepare_but_failed_run_cannot(agent_sessions, ready, status):
    async with agent_sessions.begin() as db:
        await db.execute(update(AnalysisJob).values(status=status))
    transport = Transport(ready)
    prepared = await run(agent_sessions, ready, transport)
    # run의 일반 partial은 준비 실패가 아니다. 실패한 run만 입력 불가로 막는다.
    # API는 partial을 failed로 보여 주지만 성공한 저장소의 결과·후보 조회는 허용하므로
    # (analysis-run.md 부분 실패 기준, openapi AnalysisRunResult), 그 후보로 만든 면접은 준비한다.
    if status == "partial":
        assert prepared
    else:
        assert not prepared
        assert await failure(agent_sessions, ready) == "preparation_inputs_unavailable"
        assert transport.github == [] and transport.model_operations == []


def unusable(seed):
    value = deep(seed)
    value["notable_areas"] = [dict(area(), path="missing.py")]
    return value


async def test_preparation_fails_when_no_primary_has_a_verified_area(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None, notable_areas=None)
        )
    transport = Transport(ready, miss=True)
    transport.outputs[1] = unusable(ready)
    assert not await run(agent_sessions, ready, transport)
    assert await failure(agent_sessions, ready) == "l2_failed"
    assert transport.model_operations == ["select", "analyze"]
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0
        assert await db.scalar(select(InterviewTurn)) is None


async def test_one_verified_primary_is_enough_and_invalid_repo_adds_no_evidence(
    agent_sessions, ready
):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(SessionRepository)
            .where(SessionRepository.repository_id == ready["repo_id"])
            .values(display_order=0)
        )
    second = await add_repository(agent_sessions, ready, 1, cached=False)
    inner = Transport(ready, miss=True)
    inner.outputs[1] = unusable({**ready, "repo_id": second[0]})
    transport = Repositories(inner, {SAMPLE: 123, second[1]: second[2]})
    assert await run(agent_sessions, ready, transport)
    assert inner.model_operations == ["select", "analyze", "plan", "review"]
    async with agent_sessions() as db:
        sources = {row.repository_id for row in await db.scalars(select(Evidence))}
        assert sources == {ready["repo_id"]}


async def run_with_source_failure(sessions, seed, transport, failed_path, fault):
    """실제 원문 수집 경로에서 파일 부재·HTTP 오류·전체 수집 시간 상한을 발생시킨다."""

    async def respond(request):
        if request.url.path == f"/repos/{SAMPLE}/contents/{failed_path}":
            assert request.url.params["ref"] == seed["sha"]
            if fault == "deadline":
                await asyncio.Event().wait()
            return httpx.Response(404 if fault == "missing" else 503)
        response = await transport(request)
        if request.url.path.endswith(f"/git/trees/{TREE}") and failed_path != PATH:
            payload = response.json()
            payload["tree"].append(dict(path=failed_path, mode="100644", type="blob", sha=BLOB))
            return httpx.Response(200, json=payload)
        return response

    config = settings().model_copy(update={"director_prepare_timeout_seconds": 0.1})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        return await prepare()(
            sessions,
            user_id=seed["owner"],
            interview_id=seed["interview_id"],
            settings=config,
            http_client=http,
        )


@pytest.mark.parametrize("fault", ["missing", "http_error", "deadline"])
async def test_cached_l2_keeps_reread_areas_when_another_area_cannot_be_read(
    agent_sessions, ready, fault
):
    missing = dict(area(), path="missing.py", observation="사라진 파일")
    cached = dict(analysis=deep(ready) | dict(notable_areas=[area(), missing]), rejected_areas=[])
    async with agent_sessions.begin() as db:
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        row.notable_areas = [area(), missing]
        row.result = cached
    transport = Transport(ready)
    assert await run_with_source_failure(agent_sessions, ready, transport, "missing.py", fault)
    # 다시 읽지 못한 area만 근거에서 빼고 한계로 남긴다. 저장소 전체를 버리거나 재분석하지 않는다
    # (0008 L2 관찰 분리, 0010 유효 area 1개 이상이면 준비 성공).
    assert transport.model_operations == ["plan", "review"]
    async with agent_sessions() as db:
        assert list(await db.scalars(select(Evidence.path))) == [PATH]
        interview = await db.get(InterviewSession, ready["interview_id"])
        notes = interview.context_state["preparation_repository_limitations"][str(ready["repo_id"])]
        assert any("missing.py" in note for note in notes)
        assert "l2_cache_source_mismatch" not in notes
        expected = {
            "deadline": "시간 상한",
            "missing": "github_file_unavailable",
            "http_error": "github_http_503",
        }[fault]
        assert any(expected in note for note in notes)
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        # 면접의 사용 범위만 좁히고 같은 SHA의 전역 캐시는 원래 관찰을 보존한다.
        assert row.status == "succeeded" and row.result == cached
        assert row.notable_areas == [area(), missing]


@pytest.mark.parametrize("fault", ["missing", "http_error", "deadline"])
async def test_cached_l2_without_any_reread_area_fails_without_reanalysis(
    agent_sessions, ready, fault
):
    transport = Transport(ready)
    assert not await run_with_source_failure(agent_sessions, ready, transport, PATH, fault)
    expected = (
        "repository_source_timeout" if fault == "deadline" else "repository_sources_unavailable"
    )
    assert await failure(agent_sessions, ready) == expected
    assert transport.model_operations == []
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0
        assert await db.scalar(select(InterviewTurn)) is None
        interview = await db.get(InterviewSession, ready["interview_id"])
        notes = interview.context_state["preparation_repository_limitations"][str(ready["repo_id"])]
        assert expected in notes
        assert any(PATH in note for note in notes)
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        assert row.status == "succeeded" and row.notable_areas == [area()]
        assert row.result == dict(analysis=deep(ready), rejected_areas=[])


@pytest.mark.parametrize("field", ["prompt_version", "head_sha"])
async def test_l2_cache_is_reused_only_for_matching_sha_and_prompt(agent_sessions, ready, field):
    stale = dict(prompt_version="repo_deep_v0", head_sha="e" * 40)[field]
    async with agent_sessions.begin() as db:
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        setattr(row, field, stale)
        stale_id = row.id
    transport = Transport(ready, miss=True)
    assert await run(agent_sessions, ready, transport)
    # 맞지 않는 캐시는 재사용하지 않고 현재 SHA·prompt로 새로 분석하며 기존 행을 덮지 않는다.
    assert transport.model_operations == ["select", "analyze", "plan", "review"]
    async with agent_sessions() as db:
        rows = list(
            await db.scalars(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        )
        current = [row for row in rows if row.id != stale_id]
        assert getattr(next(row for row in rows if row.id == stale_id), field) == stale
        assert [(row.head_sha, row.prompt_version, row.status) for row in current] == [
            (ready["sha"], "repo_deep_v1", "succeeded")
        ]
        assert await db.scalar(select(Evidence.path)) == PATH
