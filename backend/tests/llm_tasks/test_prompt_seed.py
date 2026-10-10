from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.llm_tasks.prompt_loader import PromptSpec
from scripts.seed_prompt_versions import (
    PROMPT_VERSIONS,
    PromptSeedValidationError,
    PromptVersionConflictError,
    seed_prompt_versions,
)


def _prompts():
    return [
        PromptSpec(
            task_name=task_name,
            version=version,
            model="test-model",
            template=f"Externally reviewed body for {task_name}.",
        )
        for task_name, version in PROMPT_VERSIONS.items()
    ]


class _Mappings:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class _SeedSession:
    def __init__(self):
        self.rows = {}
        self.locked = set()
        self.sql = []

    async def execute(self, statement, params):
        sql = " ".join(str(statement).split())
        self.sql.append(sql)
        task_name = params["task_name"]
        if "pg_advisory_xact_lock" in sql:
            self.locked.add(task_name)
            return _Result()
        if "SELECT model, template, is_active" in sql:
            row = self.rows.get((task_name, params["version"]))
            return _Result(dict(row) if row else None)

        assert task_name in self.locked, "prompt mutation must hold the task advisory lock"
        if sql.startswith("UPDATE prompt_versions SET is_active = FALSE"):
            for (stored_task, stored_version), row in self.rows.items():
                if stored_task == task_name and stored_version != params["version"]:
                    row["is_active"] = False
            return _Result()
        if sql.startswith("INSERT INTO prompt_versions"):
            self.rows[(task_name, params["version"])] = {
                "model": params["model"],
                "template": params["template"],
                "is_active": True,
            }
            return _Result()
        if sql.startswith("UPDATE prompt_versions SET is_active = TRUE"):
            self.rows[(task_name, params["version"])]["is_active"] = True
            return _Result()
        raise AssertionError(f"unexpected SQL: {sql}")


async def test_seed_is_idempotent_and_activates_all_reviewed_versions():
    session = _SeedSession()
    prompts = _prompts()

    await seed_prompt_versions(session, prompts)
    snapshot = {key: dict(value) for key, value in session.rows.items()}
    await seed_prompt_versions(session, prompts)

    assert session.rows == snapshot
    assert len(session.rows) == 7
    assert all(row["is_active"] for row in session.rows.values())


async def test_seed_rejects_changed_body_for_existing_version():
    session = _SeedSession()
    prompts = _prompts()
    await seed_prompt_versions(session, prompts)
    changed = _prompts()
    changed[0] = replace(changed[0], template="unreviewed replacement")

    with pytest.raises(PromptVersionConflictError):
        await seed_prompt_versions(session, changed)


async def test_seed_rejects_blank_external_body_before_database_access():
    session = _SeedSession()
    prompts = _prompts()
    prompts[0] = SimpleNamespace(
        task_name=prompts[0].task_name,
        version=prompts[0].version,
        model=prompts[0].model,
        template="   ",
    )

    with pytest.raises(PromptSeedValidationError):
        await seed_prompt_versions(session, prompts)

    assert session.rows == {}
    assert session.locked == set()


async def test_seed_requires_exactly_the_seven_fixed_task_versions():
    session = _SeedSession()

    with pytest.raises(PromptSeedValidationError):
        await seed_prompt_versions(session, _prompts()[:-1])

    assert session.rows == {}


async def test_seed_serializes_activation_per_task_and_replaces_old_active_version():
    session = _SeedSession()
    session.rows[("repo_shallow", "repo_shallow_v0")] = {
        "model": "old-model",
        "template": "old body",
        "is_active": True,
    }

    await seed_prompt_versions(session, _prompts())

    assert session.rows[("repo_shallow", "repo_shallow_v0")]["is_active"] is False
    assert session.rows[("repo_shallow", "repo_shallow_v1")]["is_active"] is True
    assert session.locked == set(PROMPT_VERSIONS)


async def test_seed_repairs_an_extra_active_version_without_rewriting_the_target():
    session = _SeedSession()
    prompts = _prompts()
    target = prompts[0]
    session.rows[(target.task_name, target.version)] = {
        "model": target.model,
        "template": target.template,
        "is_active": True,
    }
    session.rows[(target.task_name, "older_version")] = {
        "model": "old-model",
        "template": "old body",
        "is_active": True,
    }

    await seed_prompt_versions(session, prompts)

    assert session.rows[(target.task_name, target.version)]["is_active"] is True
    assert session.rows[(target.task_name, "older_version")]["is_active"] is False
    assert any("SET is_active = FALSE, updated_at = now()" in sql for sql in session.sql)
