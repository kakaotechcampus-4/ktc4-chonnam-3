from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from app.llm_tasks.prompt_loader import PromptSpec
from scripts import seed_prompt_versions as seeds
from tests.llm_tasks.test_prompt_seed import _SeedSession

PROMPT = PromptSpec("repo_shallow", "repo_shallow_v2", "local-model", "검수된 L1 본문")


async def test_registers_one_explicit_version_idempotently_from_an_iterable():
    session = _SeedSession()

    await seeds.register_prompt_versions(session, iter([PROMPT]))
    before = {key: dict(row) for key, row in session.rows.items()}
    await seeds.register_prompt_versions(session, [PROMPT])

    assert (
        session.rows
        == before
        == {
            ("repo_shallow", "repo_shallow_v2"): {
                "model": "local-model",
                "template": "검수된 L1 본문",
                "is_active": True,
            }
        }
    )
    assert session.locked == {"repo_shallow"}


@pytest.mark.parametrize("field", ["model", "template"])
async def test_same_version_rejects_changed_content_without_mutation(field):
    session = _SeedSession()
    await seeds.register_prompt_versions(session, [PROMPT])
    before = {key: dict(row) for key, row in session.rows.items()}

    with pytest.raises(seeds.PromptVersionConflictError):
        await seeds.register_prompt_versions(session, [replace(PROMPT, **{field: "changed"})])

    assert session.rows == before


async def test_new_model_activates_new_version_and_preserves_other_tasks():
    session = _SeedSession()
    old = replace(PROMPT, version="repo_shallow_v1", model="original-model")
    other = PromptSpec("director", "director_v1", "original-model", "검수된 질문 본문")
    await seeds.register_prompt_versions(session, [old, other])
    other_before = dict(session.rows[("director", "director_v1")])

    await seeds.register_prompt_versions(session, [PROMPT])

    assert session.rows[("repo_shallow", "repo_shallow_v1")] == {
        "model": "original-model",
        "template": "검수된 L1 본문",
        "is_active": False,
    }
    assert session.rows[("repo_shallow", "repo_shallow_v2")]["is_active"] is True
    assert session.rows[("director", "director_v1")] == other_before


@pytest.mark.parametrize(
    "prompts",
    [
        [],
        [replace(PROMPT, task_name="unknown_task")],
        [PROMPT, PROMPT],
        [PROMPT, replace(PROMPT, version="repo_shallow_v3")],
        *[
            [SimpleNamespace(**(asdict(PROMPT) | {field: "   "}))]
            for field in ("version", "model", "template")
        ],
    ],
    ids=[
        "empty",
        "unknown",
        "duplicate",
        "two_versions",
        "blank_version",
        "blank_model",
        "blank_body",
    ],
)
async def test_invalid_registration_is_rejected_before_database_access(prompts):
    session = _SeedSession()

    with pytest.raises(seeds.PromptSeedValidationError):
        await seeds.register_prompt_versions(session, prompts)

    assert session.sql == []


async def test_later_version_conflict_leaves_all_earlier_tasks_unchanged():
    session = _SeedSession()
    old = PromptSpec("director", "director_v1", "original-model", "검수된 질문 본문")
    await seeds.register_prompt_versions(session, [old, PROMPT])
    before = {key: dict(row) for key, row in session.rows.items()}

    with pytest.raises(seeds.PromptVersionConflictError):
        await seeds.register_prompt_versions(
            session,
            [replace(old, version="director_v2"), replace(PROMPT, model="changed-model")],
        )

    assert session.rows == before


async def test_initial_seed_still_rejects_new_versions_even_with_all_seven_tasks():
    session = _SeedSession()
    prompts = [
        PromptSpec(task, version, "model", "검수된 본문")
        for task, version in seeds.PROMPT_VERSIONS.items()
    ]
    prompts[0] = PROMPT

    with pytest.raises(seeds.PromptSeedValidationError):
        await seeds.seed_prompt_versions(session, prompts)

    assert session.sql == []


async def test_report_score_can_be_registered_with_its_own_version():
    session = _SeedSession()
    prompt = PromptSpec("report_score", "report_score_v1", "local-model", "검수된 점수 판정 본문")

    await seeds.register_prompt_versions(session, [prompt])

    assert session.rows[("report_score", "report_score_v1")]["is_active"] is True
    assert session.locked == {"report_score"}


async def test_initial_seed_stays_at_the_seven_fixed_tasks_without_report_score():
    # report_score는 초기 seed에 끼우지 않는다: 일곱 task + report_score는 거절된다.
    session = _SeedSession()
    prompts = [
        PromptSpec(task, version, "model", "검수된 본문")
        for task, version in (seeds.PROMPT_VERSIONS | seeds.ADDITIONAL_PROMPT_VERSIONS).items()
    ]

    with pytest.raises(seeds.PromptSeedValidationError):
        await seeds.seed_prompt_versions(session, prompts)

    assert session.sql == []
    assert "report_score" not in seeds.PROMPT_VERSIONS


async def test_unknown_task_is_still_rejected_for_registration():
    session = _SeedSession()
    with pytest.raises(seeds.PromptSeedValidationError):
        await seeds.register_prompt_versions(session, [PromptSpec("report_other", "v1", "m", "b")])
    assert session.sql == []


def test_register_prompt_cli_accepts_report_score_and_rejects_unknown_tasks(
    capsys, monkeypatch, tmp_path
):
    from scripts import register_prompt

    async def fake_register(task, version, template):
        return PromptSpec(task, version, "local-model", "검수된 본문")

    monkeypatch.setattr(register_prompt, "register", fake_register)
    args = ["--version", "v1", "--template", str(tmp_path / "body.md")]

    assert register_prompt.main(["--task", "report_score", *args]) == 0
    assert "task=report_score" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        register_prompt.main(["--task", "report_other", *args])
    assert "invalid choice" in capsys.readouterr().err
