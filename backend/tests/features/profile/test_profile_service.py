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


async def test_new_completed_interview_and_input_regenerate_role_even_for_the_same_repo(
    app, db, world
):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    repo.languages = {"Python": 1, "Go": 1}
    await completed_interview(db, run, [repo])
    generator = FakeGenerator("새 면접 진술을 반영한 요약입니다.")
    assert await refresh_summary(app, user, generator) == "updated"
    assert len(generator.calls) == 1
    summary = await read_summary(db, user)
    assert summary.role_summary == "새 면접 진술을 반영한 요약입니다."
    assert _ratios(summary) == {"Go": 50.0, "Python": 50.0}


async def test_identical_profile_input_reuses_the_successful_role_summary(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    generator = FakeGenerator("재사용할 때 호출하면 안 됩니다.")
    assert await refresh_summary(app, user, generator) == "role_kept"
    assert generator.calls == []


async def test_report_revision_only_change_reuses_actual_input_and_keeps_revision_audit(
    app, db, world
):
    from app.db.models import InterviewReport
    from app.features.profile import queries

    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    interview = await completed_interview(db, run, [repo])
    report = InterviewReport(
        interview_session_id=interview.id, headline="총평", summary="원본", total_score=70
    )
    db.add(report)
    await db.commit()
    first = FakeGenerator()
    assert await refresh_summary(app, user, first) == "updated"
    prior_fingerprint = (await read_summary(db, user)).input_fingerprint
    report.current_revision = 2
    await db.commit()
    unused = FakeGenerator()
    assert await refresh_summary(app, user, unused) == "role_kept"
    assert unused.calls == [] and len(first.calls) == 1
    assert (await read_summary(db, user)).input_fingerprint == prior_fingerprint
    versions = await queries.completed_versions(db, user_id=user.id, repo_ids=[repo.id])
    assert versions[0]["report_revision"] == 2


async def test_new_active_profile_prompt_invalidates_the_input_fingerprint(app, db, world):
    from app.db.models import PromptVersion

    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    prior = (await db.scalars(select(PromptVersion))).one()
    prior.is_active = False
    db.add(
        PromptVersion(
            task_name="profile_summary",
            version="fixture-v2",
            model="fixture-model",
            template="새 기준",
            is_active=True,
        )
    )
    await db.commit()
    generator = FakeGenerator("새 기준에 따른 요약입니다.")
    assert await refresh_summary(app, user, generator) == "updated"
    assert len(generator.calls) == 1
    assert (await read_summary(db, user)).prompt_version == "fixture-v2"


async def test_changed_answer_during_generation_does_not_publish_a_stale_summary(app, db, world):
    from sqlalchemy import update

    from app.db.models import InterviewTurn

    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    interview = await completed_interview(db, run, [repo])

    class ChangingGenerator(FakeGenerator):
        async def __call__(self, *args, **kwargs):
            value = await super().__call__(*args, **kwargs)
            async with app.state.session_factory.begin() as other:
                await other.execute(
                    update(InterviewTurn)
                    .where(InterviewTurn.interview_session_id == interview.id)
                    .values(answer_text="팀원이 담당했습니다.")
                )
            return value

    assert await refresh_summary(app, user, ChangingGenerator()) == "skipped"
    assert await read_summary(db, user) is None


async def test_changed_reasoning_policy_invalidates_profile_role_cache(app, db, world):
    from app.features.profile import service

    from .fakes import LLM

    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    await refresh_summary(app, user, FakeGenerator())
    generator = FakeGenerator("변경된 추론 설정으로 확인한 요약입니다.")
    assert (
        await service.refresh_profile_summary(
            app.state.session_factory,
            user_id=user.id,
            llm=LLM.model_copy(update={"llm_reasoning_effort": "high"}),
            http_client=None,
            generator=generator,
        )
        == "updated"
    )
    assert len(generator.calls) == 1


async def test_profile_task_timeout_is_used_but_does_not_relabel_a_reused_result(app, db, world):
    from app.features.profile import service

    from .fakes import LLM

    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])

    class Generator(FakeGenerator):
        async def __call__(self, payload, *, prompt, limits, model_call, statements):
            assert limits.timeout_seconds == 23
            return await super().__call__(
                payload, prompt=prompt, limits=limits, model_call=model_call, statements=statements
            )

    first = LLM.model_copy(update={"llm_task_timeouts": {"profile_summary": 23}})
    assert (
        await service.refresh_profile_summary(
            app.state.session_factory,
            user_id=user.id,
            llm=first,
            http_client=None,
            generator=Generator(),
        )
        == "updated"
    )
    second = LLM.model_copy(update={"llm_task_timeouts": {"profile_summary": 29}})
    unused = FakeGenerator()
    assert (
        await service.refresh_profile_summary(
            app.state.session_factory,
            user_id=user.id,
            llm=second,
            http_client=None,
            generator=unused,
        )
        == "role_kept"
    )
    assert unused.calls == []
    assert (await read_summary(db, user)).generation_limits["timeout_seconds"] == 23


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
