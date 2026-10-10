import pytest

from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result(self.rows)


async def test_load_active_prompt_returns_contract_without_leaking_session():
    session = _Session(
        [
            {
                "task_name": "repo_shallow",
                "version": "repo_shallow_v1",
                "model": "test-model",
                "template": "Review the supplied repository facts.",
            }
        ]
    )

    prompt = await load_active_prompt(session, "repo_shallow")

    assert prompt.task_name == "repo_shallow"
    assert prompt.version == "repo_shallow_v1"
    assert prompt.model == "test-model"
    assert prompt.template == "Review the supplied repository facts."
    assert session.calls[0][1] == {"task_name": "repo_shallow"}
    assert not hasattr(prompt, "session")


async def test_load_active_prompt_fails_when_no_active_version_exists():
    with pytest.raises(PromptNotFoundError):
        await load_active_prompt(_Session([]), "repo_shallow")


async def test_load_active_prompt_rejects_multiple_active_versions():
    rows = [
        {
            "task_name": "repo_shallow",
            "version": "repo_shallow_v1",
            "model": "test-model",
            "template": "first",
        },
        {
            "task_name": "repo_shallow",
            "version": "repo_shallow_v2",
            "model": "test-model",
            "template": "second",
        },
    ]

    with pytest.raises(PromptConfigurationError):
        await load_active_prompt(_Session(rows), "repo_shallow")


async def test_load_active_prompt_rejects_blank_task_name_without_querying():
    session = _Session([])

    with pytest.raises(ValueError):
        await load_active_prompt(session, "   ")

    assert session.calls == []
