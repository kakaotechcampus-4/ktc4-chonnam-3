from contextlib import asynccontextmanager
from importlib import import_module
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.llm_tasks.prompt_loader import load_active_prompt
from tests.llm_tasks.test_prompt_postgres import prompt_sessions as prompt_sessions
from tests.llm_tasks.test_prompt_seed import _SeedSession

BODY = "검수된 프롬프트 원문입니다."
DATABASE = "postgresql+asyncpg://fixture:private@db.example/fixture"


def _settings():
    return Settings(
        database_url=DATABASE,
        proxy_token="private-fixture-token",
        chat_proxy_url="https://proxy.example/namespace/v1",
        openai_model=" selected-model ",
        llm_default_model="old-model",
        llm_timeout_seconds=10,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
        _env_file=None,
    )


def _arguments(template):
    return ["--task", "repo_shallow", "--version", "l1_proxy_local_v1", "--template", str(template)]


def _database(cli, monkeypatch):
    session = _SeedSession()
    events = []

    @asynccontextmanager
    async def transaction():
        events.append("begin")
        try:
            yield session
        except Exception:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    async def dispose():
        events.append("dispose")

    monkeypatch.setattr(cli, "create_async_engine", lambda url: SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(
        cli, "async_sessionmaker", lambda engine: SimpleNamespace(begin=transaction)
    )
    monkeypatch.setattr(cli, "get_settings", _settings)
    return session, events


def test_cli_registers_utf8_prompt_with_the_resolved_model_and_one_transaction(
    monkeypatch, tmp_path, capsys
):
    cli = import_module("scripts.register_prompt")
    session, events = _database(cli, monkeypatch)
    template = tmp_path / "reviewed.md"
    template.write_text(BODY, encoding="utf-8")

    assert cli.main(_arguments(template)) == 0

    assert session.rows == {
        ("repo_shallow", "l1_proxy_local_v1"): {
            "model": "selected-model",
            "template": BODY,
            "is_active": True,
        }
    }
    assert events == ["begin", "commit", "dispose"]
    output = capsys.readouterr()
    assert output.out.strip() == "task=repo_shallow version=l1_proxy_local_v1 model=selected-model"
    assert output.err == ""


def test_database_failure_rolls_back_disposes_and_hides_sensitive_details(
    monkeypatch, tmp_path, capsys
):
    cli = import_module("scripts.register_prompt")
    _, events = _database(cli, monkeypatch)
    template = tmp_path / "reviewed.md"
    template.write_text(BODY, encoding="utf-8")

    async def fail(session, prompts):
        raise RuntimeError(f"{DATABASE} private-fixture-token {BODY}")

    monkeypatch.setattr(cli, "register_prompt_versions", fail)

    assert cli.main(_arguments(template)) == 1
    assert events == ["begin", "rollback", "dispose"]
    output = capsys.readouterr()
    assert output.out == ""
    assert (
        output.err.strip()
        == "Prompt registration failed. Check the file, configuration, and database."
    )


@pytest.mark.parametrize("invalid", ["missing", "encoding", "blank", "settings"])
def test_invalid_file_or_settings_fail_before_database_access(
    monkeypatch, tmp_path, capsys, invalid
):
    cli = import_module("scripts.register_prompt")
    _, events = _database(cli, monkeypatch)
    template = tmp_path / "reviewed.md"
    if invalid != "missing":
        template.write_bytes(
            b"\xff" if invalid == "encoding" else b" " if invalid == "blank" else b"ok"
        )
    if invalid == "settings":
        monkeypatch.setattr(
            cli, "get_settings", lambda: _settings().model_copy(update={"proxy_token": None})
        )

    assert cli.main(_arguments(template)) == 1
    assert events == []
    output = capsys.readouterr()
    assert output.out == "" and "Prompt registration failed." in output.err
    assert str(template) not in output.err and DATABASE not in output.err


@pytest.mark.parametrize("arguments", [[], ["--task", "unknown"], ["--model", "override"]])
def test_cli_requires_explicit_known_task_version_and_template(arguments):
    cli = import_module("scripts.register_prompt")

    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2


async def test_registration_commits_or_rolls_back_on_real_postgres(
    prompt_sessions, monkeypatch, tmp_path
):
    cli = import_module("scripts.register_prompt")
    monkeypatch.setattr(cli, "get_settings", _settings)
    monkeypatch.setattr(cli, "create_async_engine", lambda url: prompt_sessions.kw["bind"])
    template = tmp_path / "reviewed.md"
    template.write_text(BODY, encoding="utf-8")

    registered = await cli.register("repo_shallow", "l1_proxy_local_v1", template)
    async with prompt_sessions() as session:
        assert await load_active_prompt(session, "repo_shallow") == registered

    original = cli.register_prompt_versions

    async def fail_after_write(session, prompts):
        await original(session, prompts)
        raise RuntimeError("fixture transaction failure")

    monkeypatch.setattr(cli, "register_prompt_versions", fail_after_write)
    with pytest.raises(RuntimeError, match="fixture transaction failure"):
        await cli.register("repo_shallow", "l1_proxy_local_v2", template)
    async with prompt_sessions() as session:
        assert await load_active_prompt(session, "repo_shallow") == registered
