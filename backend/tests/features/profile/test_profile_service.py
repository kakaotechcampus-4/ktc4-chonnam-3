"""profile_summary 서비스. 실제 LLM 은 호출하지 않고 대역을 주입한다. task-16 / ADR 0016·0019"""

import pytest
from sqlalchemy import select

from app.db.models import RepoAnalysis
from app.llm_tasks import profile_summary as tasks

from ..interview.factories import make_repo
from .fakes import ROLE, FakeGenerator, completed_interview, read_summary, refresh_summary


def _ratios(summary):
    return {item["name"]: item["ratio"] for item in summary.languages}


async def test_same_repo_in_many_interviews_counts_once(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 100})
    for _ in range(3):
        await completed_interview(db, run, [repo])
    assert await refresh_summary(app, user, FakeGenerator()) == "updated"
    summary = await read_summary(db, user)
    assert summary.based_on_repo_count == 1
    assert summary.based_repo_ids == [repo.id]
    assert _ratios(summary) == {"Python": 100.0}
    assert summary.role_summary == ROLE
    assert (summary.model, summary.prompt_version) == ("fixture-model", "fixture-v1")


async def test_python_and_java_repos_split_fifty_fifty_with_sorted_ids(app, db, world):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 9_000_000})
    second = await make_repo(db, run, languages={"Java": 5})
    await completed_interview(db, run, [second, first])
    await completed_interview(db, run, [first])
    await refresh_summary(app, user, FakeGenerator())
    summary = await read_summary(db, user)
    assert _ratios(summary) == {"Java": 50.0, "Python": 50.0}
    assert summary.based_on_repo_count == 2
    assert summary.based_repo_ids == sorted([first.id, second.id])


async def test_only_completed_interview_repos_are_counted(app, db, world):
    user, run = world
    used = await make_repo(db, run, languages={"Python": 1})
    other = await make_repo(db, run, languages={"Go": 1})
    await completed_interview(db, run, [used])
    await completed_interview(db, run, [other], status="in_progress")
    await refresh_summary(app, user, FakeGenerator())
    assert _ratios(await read_summary(db, user)) == {"Python": 100.0}


@pytest.mark.parametrize("bad", [None, {}])
async def test_missing_language_data_fails_without_calling_llm(app, db, world, bad):
    user, run = world
    good = await make_repo(db, run, languages={"Python": 1})
    broken = await make_repo(db, run, languages=bad)
    await completed_interview(db, run, [good, broken])
    generator = FakeGenerator()
    with pytest.raises(tasks.LanguageDataMissingError):
        await refresh_summary(app, user, generator)
    assert generator.calls == []
    assert await read_summary(db, user) is None


async def test_missing_language_data_keeps_previous_summary(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    broken = await make_repo(db, run, languages=None)
    await completed_interview(db, run, [broken])
    with pytest.raises(tasks.LanguageDataMissingError):
        await refresh_summary(app, user, FakeGenerator("새 요약입니다."))
    summary = await read_summary(db, user)
    assert summary.role_summary == ROLE
    assert summary.based_repo_ids == [repo.id]
    assert _ratios(summary) == {"Python": 100.0}


async def test_same_repo_set_does_not_call_llm_and_keeps_role_summary(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    repo.languages = {"Python": 1, "Go": 1}
    await completed_interview(db, run, [repo])
    generator = FakeGenerator("바뀌면 안 되는 요약입니다.")
    assert await refresh_summary(app, user, generator) == "role_kept"
    assert generator.calls == []
    summary = await read_summary(db, user)
    assert summary.role_summary == ROLE
    assert _ratios(summary) == {"Go": 50.0, "Python": 50.0}


async def test_changed_repo_set_regenerates_role_summary(app, db, world):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    await refresh_summary(app, user, FakeGenerator())
    second = await make_repo(db, run, languages={"Java": 1})
    await completed_interview(db, run, [second])
    generator = FakeGenerator("두 저장소 기준 요약입니다.")
    assert await refresh_summary(app, user, generator) == "updated"
    assert len(generator.calls) == 1
    assert (await read_summary(db, user)).role_summary == "두 저장소 기준 요약입니다."


async def test_llm_failure_keeps_previous_summary(app, db, world):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    await refresh_summary(app, user, FakeGenerator())
    second = await make_repo(db, run, languages={"Java": 1})
    await completed_interview(db, run, [second])
    with pytest.raises(tasks.RoleSummaryCallError):
        await refresh_summary(
            app, user, FakeGenerator(error=tasks.RoleSummaryCallError("llm_timeout"))
        )
    summary = await read_summary(db, user)
    assert summary.role_summary == ROLE
    assert summary.based_repo_ids == [first.id]
    assert summary.based_on_repo_count == 1


async def test_no_interview_statements_fails_instead_of_guessing(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo], answered=False)
    generator = FakeGenerator()
    with pytest.raises(tasks.RoleEvidenceMissingError):
        await refresh_summary(app, user, generator)
    assert generator.calls == []
    assert await read_summary(db, user) is None


async def test_payload_separates_facts_from_statements_and_project_types(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1}, description="결제 서비스")
    shallow = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
    shallow.result = {
        "repository_id": str(repo.id),
        "head_sha": "a" * 40,
        "purpose": "p",
        "key_features": ["f"],
        "project_types": ["backend", "web"],
        "tech_stack": ["Python"],
        "project_role_summary": "프로젝트 역할 설명",
        "basis": [{"kind": "readme", "claim": "c"}],
        "limitations": [],
    }
    await completed_interview(db, run, [repo])
    generator = FakeGenerator()
    await refresh_summary(app, user, generator)
    payload, statements = generator.calls[0]
    assert statements == ["인증 API 를 만들었습니다."]
    assert payload["interview_statements"][0]["repositories"] == [repo.name]
    assert payload["repository_facts"][0]["description"] == "결제 서비스"
    assert "프로젝트 역할 설명" not in str(payload)
    assert (await read_summary(db, user)).project_types == ["backend", "web"]
