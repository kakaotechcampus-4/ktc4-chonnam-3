"""고정 ref·선택 범위와 Evidence 원문의 실제 PostgreSQL 저장을 검증한다."""

from dataclasses import replace
from importlib import import_module, util
from uuid import UUID, uuid4

import pytest
from devon_ai import contracts as c
from sqlalchemy import delete, func, select, update

from app.db.models import (
    Evidence,
    InterviewSession,
    RepoAnalysis,
    Repository,
    SessionRepository,
    User,
)
from app.features.interview.agent_context import AgentStateError


def queries():
    name = "app.features.interview.agent_queries"
    assert util.find_spec(name) is not None, "Evidence 저장 경계가 필요하다"
    return import_module(name)


def item(seed, **changes):
    return replace(
        c.Evidence(
            None,
            str(seed["repo_id"]),
            seed["sha"],
            "file",
            "src/main.py",
            None,
            "first\nsecond",
            "read_file",
            "실제 원문",
            10,
            11,
        ),
        **changes,
    )


async def scope(db, seed, user_id=None):
    return await queries().load_evidence_scope(
        db,
        user_id=user_id or seed["owner"],
        interview_id=seed["interview_id"],
        repository_id=seed["repo_id"],
    )


async def store(db, seed, items, user_id=None):
    return await queries().store_evidence(
        db,
        user_id=user_id or seed["owner"],
        interview_id=seed["interview_id"],
        items=items,
    )


async def test_scope_uses_fixed_sha_l2_and_existing_file_sources_only(agent_sessions, agent_seed):
    async with agent_sessions.begin() as db:
        await db.execute(update(Repository).values(head_sha="b" * 40))
        await db.execute(
            update(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2").values(status="partial")
        )
        db.add(
            RepoAnalysis(
                repository_id=agent_seed["repo_id"],
                analysis_level="l2",
                head_sha="b" * 40,
                prompt_version="new",
                model="fixture",
                status="succeeded",
                notable_areas=[{"path": "new.py"}],
            )
        )
        for path, ref, source in (
            ("README.md", agent_seed["sha"], "readme"),
            ("old.py", "b" * 40, "file"),
            ("metadata.py", agent_seed["sha"], "repo_metadata"),
        ):
            db.add(
                Evidence(
                    interview_session_id=agent_seed["interview_id"],
                    repository_id=agent_seed["repo_id"],
                    source_type=source,
                    git_ref=ref,
                    path=path,
                    snippet="원문",
                )
            )
    async with agent_sessions() as db:
        result = await scope(db, agent_seed)
    assert result.git_ref == agent_seed["sha"]
    assert result.allowed_paths == frozenset({"src/main.py", "README.md"})


@pytest.mark.parametrize(
    "case", ["foreign", "ended", "inactive", "private", "inaccessible", "no_sha"]
)
async def test_scope_rejects_unavailable_or_unfixed_repository(agent_sessions, agent_seed, case):
    async with agent_sessions.begin() as db:
        if case == "ended":
            await db.execute(update(InterviewSession).values(status="completed"))
        elif case == "inactive":
            await db.execute(
                update(User).where(User.id == agent_seed["owner"]).values(status="suspended")
            )
        elif case == "private":
            await db.execute(update(Repository).values(is_private=True))
        elif case == "inaccessible":
            await db.execute(update(Repository).values(is_accessible=False))
        elif case == "no_sha":
            await db.execute(update(SessionRepository).values(snapshot_head_sha=None))
    async with agent_sessions() as db:
        with pytest.raises(AgentStateError):
            await scope(db, agent_seed, agent_seed["other"] if case == "foreign" else None)


async def test_scope_does_not_invent_readme_when_no_paths_are_known(agent_sessions, agent_seed):
    async with agent_sessions.begin() as db:
        await db.execute(delete(RepoAnalysis))
    async with agent_sessions() as db:
        assert (await scope(db, agent_seed)).allowed_paths == frozenset()


async def test_source_roundtrip_and_replay_preserve_one_durable_id(agent_sessions, agent_seed):
    original = item(agent_seed)
    async with agent_sessions.begin() as db:
        (saved,) = await store(db, agent_seed, (original,))
        async with agent_sessions() as observer:
            assert await observer.scalar(select(func.count()).select_from(Evidence)) == 0
    assert saved.evidence_id is not None
    assert replace(saved, evidence_id=None) == original
    async with agent_sessions.begin() as db:
        assert await store(db, agent_seed, (saved,)) == (saved,)
    async with agent_sessions() as db:
        row = await db.get(Evidence, UUID(saved.evidence_id))
        assert row.snippet == original.content and row.summary == original.summary
        assert (row.start_line, row.end_line, row.git_ref) == (10, 11, agent_seed["sha"])
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"content": "forged\nsecond"},
        {"summary": "변조"},
        {"start_line": 20, "end_line": 21},
        {"tool_name": "different_tool"},
        {"source_kind": "readme"},
    ],
)
async def test_existing_id_cannot_rewrite_source_fields(agent_sessions, agent_seed, change):
    async with agent_sessions.begin() as db:
        (saved,) = await store(db, agent_seed, (item(agent_seed),))
    async with agent_sessions.begin() as db:
        with pytest.raises(AgentStateError):
            await store(db, agent_seed, (replace(saved, **change),))
    async with agent_sessions() as db:
        row = await db.get(Evidence, UUID(saved.evidence_id))
        assert row.snippet == "first\nsecond" and row.tool_name == "read_file"


@pytest.mark.parametrize(
    "change",
    [
        {"git_ref": "b" * 40},
        {"path": "src/other.py"},
        {"repository_id": str(uuid4())},
        {"evidence_id": str(uuid4())},
        {
            "source_kind": "languages",
            "path": None,
            "metadata_key": "languages",
            "start_line": None,
            "end_line": None,
        },
        {"end_line": 12},
    ],
)
async def test_invalid_item_never_partially_writes_a_batch(agent_sessions, agent_seed, change):
    async with agent_sessions.begin() as db:
        with pytest.raises(AgentStateError):
            await store(db, agent_seed, (item(agent_seed), item(agent_seed, **change)))
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0


async def test_caller_rollback_removes_stored_partial_tool_items(agent_sessions, agent_seed):
    result = c.ToolResult(
        "tool_error",
        (item(agent_seed),),
        ("src/main.py",),
        ("후속 파일 조회 실패",),
        "github_timeout",
    )
    async with agent_sessions() as db:
        saved = await store(db, agent_seed, result.items)
        assert saved[0].evidence_id is not None
        await db.rollback()
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0


@pytest.mark.parametrize("case", ["foreign", "ended", "new_ref"])
async def test_store_rechecks_permission_after_scope_was_loaded(agent_sessions, agent_seed, case):
    async with agent_sessions() as db:
        await scope(db, agent_seed)
    async with agent_sessions.begin() as db:
        if case == "ended":
            await db.execute(update(InterviewSession).values(status="abandoned"))
        elif case == "new_ref":
            await db.execute(update(SessionRepository).values(snapshot_head_sha="b" * 40))
    async with agent_sessions.begin() as db:
        with pytest.raises(AgentStateError):
            await store(
                db,
                agent_seed,
                (item(agent_seed),),
                agent_seed["other"] if case == "foreign" else None,
            )
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 0


async def test_matching_source_from_another_interview_is_not_reused(agent_sessions, agent_seed):
    other_session, other_evidence = uuid4(), uuid4()
    async with agent_sessions.begin() as db:
        current = await db.get(InterviewSession, agent_seed["interview_id"])
        db.add(
            InterviewSession(
                id=other_session,
                user_id=agent_seed["other"],
                analysis_job_id=current.analysis_job_id,
                job_posting_id=current.job_posting_id,
                status="completed",
            )
        )
        await db.flush()
        db.add(
            Evidence(
                id=other_evidence,
                interview_session_id=other_session,
                repository_id=agent_seed["repo_id"],
                git_ref=agent_seed["sha"],
                source_type="file",
                path="src/main.py",
                snippet="first\nsecond",
                summary="실제 원문",
                tool_name="read_file",
                start_line=10,
                end_line=11,
            )
        )
    async with agent_sessions.begin() as db:
        with pytest.raises(AgentStateError):
            await store(db, agent_seed, (item(agent_seed, evidence_id=str(other_evidence)),))
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Evidence)) == 1


@pytest.mark.parametrize("content", ["first\rsecond", "first\u2028second"])
async def test_file_line_numbers_count_only_lf(agent_sessions, agent_seed, content):
    original = item(agent_seed, content=content, start_line=1, end_line=1)
    async with agent_sessions.begin() as db:
        (saved,) = await store(db, agent_seed, (original,))
    async with agent_sessions() as db:
        row = await db.get(Evidence, UUID(saved.evidence_id))
        assert row.snippet == content
        assert row.start_line == row.end_line == 1
