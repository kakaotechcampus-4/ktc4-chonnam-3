"""실제 PostgreSQL과 고정 GitHub 원문으로 준비부터 첫 Director 질문까지 검증한다."""

import asyncio
import base64
import hashlib
import importlib
import json
from dataclasses import asdict

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select, update

from app.core.config import Settings
from app.db.models import (
    AnalysisRepoCandidate,
    Evidence,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    PromptVersion,
    RepoAnalysis,
    Repository,
    ScoreCriterion,
    SessionRepository,
)
from app.db.models.report import SCORE_KEYS

TEXT = "class Service:\n    pass\n"
BLOB = hashlib.sha1(f"blob {len(TEXT.encode())}\0".encode() + TEXT.encode()).hexdigest()
TREE = "c" * 40
PATH = "서비스 code.py"


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=131072,
        llm_max_response_bytes=131072,
    )


def prepare():
    function = getattr(
        importlib.import_module("app.features.interview.prepare"), "prepare_interview", None
    )
    assert callable(function), "실제 준비 실행 함수가 필요하다"
    return function


def shallow(seed):
    return c.ShallowRepoAnalysis(
        str(seed["repo_id"]),
        seed["sha"],
        "서비스",
        ("요청 처리",),
        ("backend",),
        ("Python",),
        "요청을 처리하는 프로젝트",
        (c.ShallowBasis("readme", "서비스"),),
        (),
    )


def area():
    return dict(path=PATH, observation="서비스 클래스", scope="entire file", limitations=[])


def deep(seed):
    return dict(
        repository_id=str(seed["repo_id"]),
        head_sha=seed["sha"],
        architecture_summary="서비스 클래스",
        confirmed_technologies=["Python"],
        notable_areas=[area()],
        limitations=[],
    )


def plan():
    return dict(
        question=dict(
            persona="hr_manager",
            text="프로젝트에서 맡은 역할을 소개해 주세요.",
            topic_code="role",
            question_contract=dict(
                purpose="본인 역할 소개",
                required_points=[dict(key="role", description="본인 역할")],
                assumptions=[],
                basis_refs=[],
                evaluation_scope="역할",
            ),
            evidence_refs=[],
            jd_requirement_ids=[],
        ),
        intent="역할 확인",
        reason_summary="첫 자기소개",
    )


REVIEW = dict(
    plan_valid=True,
    context_valid=True,
    wording_valid=True,
    contract_matches=True,
    safe_alternative=True,
    reason_summary="원문에 맞는 질문",
)


def response(data):
    return httpx.Response(
        200,
        json=dict(
            id="fixture",
            model="actual-fixture",
            status="completed",
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[dict(type="output_text", text=json.dumps(data, ensure_ascii=False))],
                )
            ],
        ),
    )


class Transport:
    def __init__(self, seed, *, miss=False):
        self.seed = seed
        self.model_operations = []
        self.model_payloads = []
        self.github = []
        self.outputs = [dict(selected_paths=[PATH]), deep(seed)] if miss else []
        self.outputs += [plan(), REVIEW]

    async def __call__(self, request):
        if request.method == "POST":
            body = json.loads(request.content)
            payload = json.loads(body["input"][0]["content"][0]["text"])
            self.model_operations.append(payload.get("operation", "analyze"))
            self.model_payloads.append(payload)
            return response(self.outputs.pop(0))
        self.github.append(request)
        suffix = request.url.path.removeprefix("/repos/owner/sample")
        if not suffix:
            return httpx.Response(200, json=dict(id=123, private=False))
        if suffix == f"/git/commits/{self.seed['sha']}":
            return httpx.Response(200, json=dict(sha=self.seed["sha"], tree=dict(sha=TREE)))
        if suffix == f"/git/trees/{TREE}":
            return httpx.Response(
                200,
                json=dict(
                    sha=TREE,
                    truncated=False,
                    tree=[
                        dict(
                            path=PATH,
                            mode="100644",
                            type="blob",
                            sha=BLOB,
                        )
                    ],
                ),
            )
        if suffix == f"/contents/{PATH}":
            assert request.url.params["ref"] == self.seed["sha"]
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path=PATH,
                    sha=BLOB,
                    size=len(TEXT.encode()),
                    encoding="base64",
                    content=base64.b64encode(TEXT.encode()).decode(),
                ),
            )
        raise AssertionError(f"예상하지 않은 GitHub 경로: {suffix}")


@pytest.fixture
async def ready(agent_sessions, agent_seed):
    async with agent_sessions.begin() as db:
        await db.execute(update(InterviewSession).values(status="preparing"))
        await db.execute(update(Repository).values(head_sha="b" * 40))
        l1 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l1"))
        l1.result = asdict(shallow(agent_seed))
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        db.add(
            AnalysisRepoCandidate(
                analysis_job_id=interview.analysis_job_id,
                repository_id=agent_seed["repo_id"],
                base_rank=1,
                batch_no=1,
                batch_rank=1,
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
        l2 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        l2.prompt_version = "repo_deep_v1"
        l2.notable_areas = [area()]
        l2.result = dict(analysis=deep(agent_seed), rejected_areas=[])
        for task in ("repo_deep", "answer_analysis"):
            db.add(
                PromptVersion(
                    task_name=task,
                    version=f"{task}_v1",
                    model="fixture",
                    template="fixture",
                    is_active=True,
                )
            )
        for index, key in enumerate(SCORE_KEYS):
            db.add(
                ScoreCriterion(
                    score_key=key,
                    label_ko=key,
                    rubric={"verified": True},
                    display_order=index,
                    is_active=True,
                )
            )
    return agent_seed


async def run(sessions, seed, transport):
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        return await prepare()(
            sessions,
            user_id=seed["owner"],
            interview_id=seed["interview_id"],
            settings=settings(),
            http_client=http,
        )


async def test_cached_l2_reads_real_fixed_source_and_starts_actual_director(agent_sessions, ready):
    transport = Transport(ready)
    success = await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert success, row.last_error
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        selected = await db.scalar(select(SessionRepository))
        evidence = await db.scalar(select(Evidence))
        turn = await db.scalar(select(InterviewTurn))
        # 준비 완료는 타이머를 시작하지 않는다. started_at 은 시작 클릭이 기록한다(#259).
        assert interview.status == "in_progress" and interview.started_at is None
        assert interview.last_error is None and interview.current_turn == 1
        assert [step["status"] for step in interview.prepare_steps] == ["completed"] * 4
        assert selected.snapshot_head_sha == ready["sha"] and selected.is_primary
        assert evidence.snippet == TEXT and evidence.tool_name is None
        assert (evidence.path, evidence.git_ref, evidence.start_line, evidence.end_line) == (
            PATH,
            ready["sha"],
            1,
            2,
        )
        assert turn.question_contract is not None
    assert transport.model_operations == ["plan", "review"]


async def test_prepare_persists_tree_neighbor_as_candidate_without_inventing_evidence(
    agent_sessions, ready
):
    from app.features.interview.agent_queries import load_evidence_scope

    transport = Transport(ready)

    async def handle(request):
        result = await transport(request)
        if request.url.path.endswith(f"/git/trees/{TREE}"):
            body = result.json()
            body["tree"].append(
                dict(path="nearby.custom", mode="100644", type="blob", sha="d" * 40)
            )
            return httpx.Response(200, json=body)
        return result

    assert await run(agent_sessions, ready, handle)
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        snapshot = interview.context_state["repository_lookup_candidates"][str(ready["repo_id"])]
        assert snapshot["head_sha"] == ready["sha"] and snapshot["paths"] == [PATH, "nearby.custom"]
        scope = await load_evidence_scope(
            db,
            user_id=ready["owner"],
            interview_id=ready["interview_id"],
            repository_id=ready["repo_id"],
        )
        assert "nearby.custom" in scope.allowed_paths
        assert list(await db.scalars(select(Evidence.path))) == [PATH]
    assert transport.model_operations == ["plan", "review"]


async def test_read_file_not_highlighted_by_l2_remains_queryable_only_at_its_sha(
    agent_sessions, ready
):
    from app.features.interview.agent_queries import load_evidence_scope

    second = "read-not-highlighted.custom"
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None)
        )
    transport = Transport(ready, miss=True)
    transport.outputs[0] = {"selected_paths": [PATH, second]}

    async def handle(request):
        if request.url.path.endswith(f"/contents/{second}"):
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path=second,
                    sha=BLOB,
                    size=len(TEXT.encode()),
                    encoding="base64",
                    content=base64.b64encode(TEXT.encode()).decode(),
                ),
            )
        result = await transport(request)
        if request.url.path.endswith(f"/git/trees/{TREE}"):
            body = result.json()
            body["tree"].append(dict(path=second, mode="100644", type="blob", sha=BLOB))
            return httpx.Response(200, json=body)
        return result

    assert await run(agent_sessions, ready, handle)
    async with agent_sessions.begin() as db:
        args = dict(
            user_id=ready["owner"],
            interview_id=ready["interview_id"],
            repository_id=ready["repo_id"],
        )
        assert second in (await load_evidence_scope(db, **args)).allowed_paths
        assert list(await db.scalars(select(Evidence.path))) == [PATH]
        row = await db.get(InterviewSession, ready["interview_id"])
        state = json.loads(json.dumps(row.context_state))
        state["repository_lookup_candidates"][str(ready["repo_id"])]["head_sha"] = "f" * 40
        row.context_state = state
        await db.flush()
        assert second not in (await load_evidence_scope(db, **args)).allowed_paths


async def test_missing_active_prompt_fails_explicitly_without_external_io(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(PromptVersion)
            .where(PromptVersion.task_name == "answer_analysis")
            .values(is_active=False)
        )
    transport = Transport(ready)
    assert not await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        assert interview.status == "preparing_failed"
        assert interview.last_error["recoverable"] is True
        assert interview.last_error["code"] == "prompt_unavailable"
    assert transport.model_operations == transport.github == []


async def test_l2_miss_selects_sources_and_analyzes_with_two_total_attempts(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None, notable_areas=None)
        )
    transport = Transport(ready, miss=True)
    success = await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert success, row.last_error
    assert transport.model_operations == ["select", "analyze", "plan", "review"]
    async with agent_sessions() as db:
        l2 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        assert l2.status == "succeeded" and l2.attempt == 2


async def test_duplicate_worker_and_abandoned_result_do_not_generate_question(
    agent_sessions, ready
):
    entered, release = asyncio.Event(), asyncio.Event()
    transport = Transport(ready)

    async def delayed(request):
        entered.set()
        await release.wait()
        return await transport(request)

    task = asyncio.create_task(run(agent_sessions, ready, delayed))
    await asyncio.wait_for(entered.wait(), timeout=3)
    try:
        assert not await run(agent_sessions, ready, transport)
        async with agent_sessions.begin() as db:
            await db.execute(update(InterviewSession).values(status="abandoned"))
    finally:
        release.set()
    assert not await task
    assert transport.model_operations == []
    async with agent_sessions() as db:
        assert await db.scalar(select(InterviewTurn)) is None


@pytest.mark.parametrize("invalid", ["scope", "duplicate", "source_mismatch", "json_null"])
async def test_invalid_success_cache_is_reanalyzed_and_replaced(agent_sessions, ready, invalid):
    async with agent_sessions.begin() as db:
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        value = deep(ready)
        if invalid == "scope":
            value["notable_areas"][0]["scope"] = "unrecoverable excerpt"
        elif invalid == "duplicate":
            value["notable_areas"].append(dict(value["notable_areas"][0]))
        row.notable_areas = value["notable_areas"] if invalid != "source_mismatch" else []
        row.result = dict(analysis=value, rejected_areas=[])
        if invalid == "json_null":
            row.notable_areas, row.result = None, None
    transport = Transport(ready, miss=True)
    assert await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        row = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        assert row.notable_areas == [area()]
        assert row.result["analysis"]["notable_areas"] == [area()]


async def test_invalid_selection_stops_after_one_call_and_keeps_raw_attempt(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None, notable_areas=None)
        )
    transport = Transport(ready, miss=True)
    transport.outputs[0] = dict(selected_paths=["unread.py"])
    assert not await run(agent_sessions, ready, transport)
    assert transport.model_operations == ["select"]
    assert (
        transport.model_payloads[0]["max_selected_files"] == settings().director_prepare_max_files
    )
    async with agent_sessions() as db:
        record = await db.scalar(
            select(LLMCallRecord).where(LLMCallRecord.task_name == "repo_deep")
        )
        assert len(record.attempts) == 1
        assert "unread.py" in record.attempts[0]["raw_output"]
        assert record.attempts[0]["error_stage"] == "semantic"


@pytest.mark.parametrize("case", ["private", "wrong_sha", "bad_blob"])
async def test_untrusted_github_source_never_starts_director(agent_sessions, ready, case):
    transport = Transport(ready)

    async def invalid(request):
        response = await transport(request)
        value = response.json()
        if case == "private" and request.url.path.endswith("/owner/sample"):
            value["private"] = True
        if case == "wrong_sha" and "/git/trees/" in request.url.path:
            value["sha"] = "d" * 40
        if case == "bad_blob" and "/contents/" in request.url.path:
            value["content"] = base64.b64encode(b"different").decode()
        return httpx.Response(200, json=value)

    assert not await run(agent_sessions, ready, invalid)
    assert transport.model_operations == []
    async with agent_sessions() as db:
        assert await db.scalar(select(Evidence)) is None
        assert await db.scalar(select(InterviewTurn)) is None


async def test_registered_worker_uses_context_and_duplicate_delivery_reuses_question(
    agent_sessions, ready
):
    from app.workers.tasks.interview_prep import interview_prep

    transport = Transport(ready, miss=True)
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None, notable_areas=None)
        )
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        ctx = dict(session_factory=agent_sessions, settings=settings(), http_client=http)
        await interview_prep(ctx, str(ready["interview_id"]))
        await interview_prep(ctx, str(ready["interview_id"]))
    assert transport.model_operations == ["select", "analyze", "plan", "review"]
    async with agent_sessions() as db:
        records = (await db.scalars(select(LLMCallRecord).order_by(LLMCallRecord.created_at))).all()
        assert [[item["attempt"] for item in row.attempts] for row in records] == [[1, 2], [1, 2]]


@pytest.mark.parametrize("invalid", ["contract", "basis"])
async def test_invalid_existing_first_question_becomes_preparation_failure(
    agent_sessions, ready, invalid
):
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        row.current_turn = 1
        stored = {"invalid": True}
        if invalid == "basis":
            stored = plan()["question"]["question_contract"]
            stored["basis_refs"] = [
                dict(kind="evidence", id="00000000-0000-0000-0000-000000000001")
            ]
        db.add(
            InterviewTurn(
                interview_session_id=row.id,
                turn_no=1,
                persona="hr_manager",
                question_text="기존 질문",
                question_contract=stored,
                topic_code="role",
            )
        )
    transport = Transport(ready)
    assert not await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.status == "preparing_failed"
        assert row.last_error["code"] == "prepared_question_invalid"
    assert transport.model_operations == transport.github == []


async def test_canceled_source_fetch_keeps_completed_selection_attempt(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        await db.execute(
            update(RepoAnalysis)
            .where(RepoAnalysis.analysis_level == "l2")
            .values(status="failed", result=None, notable_areas=None)
        )
    entered = asyncio.Event()
    transport = Transport(ready, miss=True)

    async def pending(request):
        if "/contents/" in request.url.path:
            entered.set()
            await asyncio.Event().wait()
        return await transport(request)

    task = asyncio.create_task(run(agent_sessions, ready, pending))
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        record = await db.scalar(
            select(LLMCallRecord).where(LLMCallRecord.task_name == "repo_deep")
        )
        assert row.status == "preparing_failed"
        assert "prepare_job_id" not in row.context_state
        assert record.discard_reason == "canceled" and len(record.attempts) == 1
        assert record.attempts[0]["schema_version"] == "1"
        assert PATH in record.attempts[0]["raw_output"]
    assert transport.model_operations == ["select"]


async def test_changed_selection_releases_owned_claim_and_allows_retry(agent_sessions, ready):
    transport = Transport(ready)
    changed = False

    async def stale(request):
        nonlocal changed
        if not changed:
            async with agent_sessions.begin() as db:
                await db.execute(update(SessionRepository).values(snapshot_head_sha="f" * 40))
            changed = True
        return await transport(request)

    assert not await run(agent_sessions, ready, stale)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.status == "preparing_failed"
        assert "prepare_job_id" not in row.context_state
        assert row.last_error["code"] == "preparation_changed"
        assert await db.scalar(select(Evidence)) is None


async def test_collector_limits_are_forwarded_to_the_actual_l2_model():
    from uuid import UUID

    from app.llm_tasks.repo_deep import analyze_repository

    seed = dict(repo_id=UUID(int=1), sha="a" * 40)
    transport = Transport(seed)
    transport.outputs = [deep(seed)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await analyze_repository(
            c.DeepRepoInput(
                str(seed["repo_id"]),
                seed["sha"],
                shallow(seed),
                (c.SourceDocument(PATH, "file", TEXT, "entire file"),),
            ),
            snapshot_head_sha=seed["sha"],
            prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
            settings=settings().require_llm(),
            http_client=http,
            source_limitations=("구조 깊이 상한으로 나머지 파일은 확인하지 못했습니다.",),
        )
    assert result.succeeded
    assert transport.model_payloads[0]["source_limitations"] == [
        "구조 깊이 상한으로 나머지 파일은 확인하지 못했습니다.",
    ]


async def test_committed_valid_first_question_recovers_without_model_call(agent_sessions, ready):
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        row.current_turn = 1
        row.context_state = dict(prepare_job_id="previous-worker", preserved="원본")
        db.add(
            InterviewTurn(
                interview_session_id=row.id,
                turn_no=1,
                persona="hr_manager",
                topic_code="role",
                question_text="프로젝트에서 맡은 역할을 소개해 주세요.",
                question_contract=plan()["question"]["question_contract"],
            )
        )
    transport = Transport(ready)
    assert await run(agent_sessions, ready, transport)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.status == "in_progress" and row.context_state == dict(preserved="원본")
    assert transport.model_operations == transport.github == []


async def test_interview_started_recorded_once_for_duplicate_delivery(agent_sessions, ready):
    from tests.event_helpers import names

    transport = Transport(ready)
    assert await run(agent_sessions, ready, transport)
    assert not await run(agent_sessions, ready, Transport(ready))
    async with agent_sessions() as db:
        assert await names(db, "interview_started") == ["interview_started"]


async def test_interview_started_recorded_when_committed_question_is_recovered(
    agent_sessions, ready
):
    from tests.event_helpers import names

    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        row.current_turn = 1
        db.add(
            InterviewTurn(
                interview_session_id=row.id,
                turn_no=1,
                persona="hr_manager",
                topic_code="role",
                question_text="프로젝트에서 맡은 역할을 소개해 주세요.",
                question_contract=plan()["question"]["question_contract"],
            )
        )
    assert await run(agent_sessions, ready, Transport(ready))
    async with agent_sessions() as db:
        assert await names(db, "interview_started") == ["interview_started"]
