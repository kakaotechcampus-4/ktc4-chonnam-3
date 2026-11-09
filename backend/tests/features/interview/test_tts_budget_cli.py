"""Cloud 확인 없이 무료 문자 예산을 새로 부여하지 않는 CLI 계약."""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.features.interview.tts_budget import BudgetSnapshot


def arguments() -> list[str]:
    return [
        "--project",
        "example-project",
        "--monthly-limit",
        "1000000",
        "--remaining-characters",
        "25000",
        "--cloud-usage-confirmed",
        "--no-inflight-confirmed",
    ]


@pytest.mark.parametrize("flag", ["--cloud-usage-confirmed", "--no-inflight-confirmed"])
def test_confirmation_required_before_configuration_read(monkeypatch, flag):
    cli = import_module("scripts.initialize_tts_budget")
    config = Mock(side_effect=AssertionError("must not read settings"))
    monkeypatch.setattr(cli, "get_settings", config)
    args = arguments()
    args.remove(flag)
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    config.assert_not_called()


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--remaining-characters", "-1"),
        ("--monthly-limit", "0"),
        ("--monthly-limit", "1000001"),
        ("--remaining-characters", "1000001"),
    ],
)
def test_invalid_allowance_rejected_before_initialization(monkeypatch, flag, value):
    cli = import_module("scripts.initialize_tts_budget")
    config = Mock(side_effect=AssertionError("must not read settings"))
    monkeypatch.setattr(cli, "get_settings", config)
    args = arguments()
    args[args.index(flag) + 1] = value
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    config.assert_not_called()


def setup_cli(monkeypatch):
    cli = import_module("scripts.initialize_tts_budget")
    tts = SimpleNamespace(budget_project="example-project", monthly_character_limit=1000000)
    config = SimpleNamespace(redis_url="redis://private-secret@local/1", require_tts=lambda: tts)
    monkeypatch.setattr(cli, "get_settings", lambda: config)
    redis = SimpleNamespace(aclose=AsyncMock())
    factory = Mock(return_value=redis)
    monkeypatch.setattr(cli.Redis, "from_url", factory)
    initialize = AsyncMock(return_value=BudgetSnapshot("2026-11", 25000, 0, 25000))
    monkeypatch.setattr(cli, "initialize_budget", initialize)
    return cli, tts, redis, factory, initialize


def test_explicit_confirmed_initialization_uses_runtime_settings(monkeypatch, capsys):
    cli, _, redis, factory, initialize = setup_cli(monkeypatch)
    assert cli.main(arguments()) == 0
    factory.assert_called_once_with("redis://private-secret@local/1")
    initialize.assert_awaited_once_with(
        redis,
        project="example-project",
        monthly_limit=1000000,
        remaining_characters=25000,
        period=None,
        basis="cloud_usage_confirmed",
    )
    redis.aclose.assert_awaited_once()
    output = capsys.readouterr()
    assert "period=2026-11" in output.out
    assert "remaining=25000" in output.out
    assert "private-secret" not in output.out + output.err
    assert "example-project" not in output.out + output.err
    assert "redis://" not in output.out + output.err


def test_mismatched_project_never_connects(monkeypatch, capsys):
    cli, tts, _, factory, initialize = setup_cli(monkeypatch)
    tts.budget_project = "another-project"
    assert cli.main(arguments()) == 1
    factory.assert_not_called()
    initialize.assert_not_awaited()
    assert "another-project" not in capsys.readouterr().err


def test_failure_closes_redis_and_hides_provider_details(monkeypatch, capsys):
    cli, _, redis, _, initialize = setup_cli(monkeypatch)
    initialize.side_effect = RuntimeError("redis://password@private-host secret-key")
    assert cli.main(arguments()) == 1
    redis.aclose.assert_awaited_once()
    output = capsys.readouterr()
    assert output.out == ""
    assert "secret-key" not in output.err
    assert "private-host" not in output.err


def test_help_does_not_read_configuration(monkeypatch, capsys):
    cli = import_module("scripts.initialize_tts_budget")
    config = Mock(side_effect=AssertionError("must not read settings"))
    monkeypatch.setattr(cli, "get_settings", config)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    config.assert_not_called()
    assert "--cloud-usage-confirmed" in capsys.readouterr().out


def test_next_month_can_be_initialized_explicitly(monkeypatch):
    cli, _, _, _, initialize = setup_cli(monkeypatch)
    assert cli.main(arguments() + ["--period", "2026-12"]) == 0
    assert initialize.await_args.kwargs["period"] == "2026-12"


def test_invalid_period_does_not_read_configuration(monkeypatch):
    cli = import_module("scripts.initialize_tts_budget")
    config = Mock(side_effect=AssertionError("must not read settings"))
    monkeypatch.setattr(cli, "get_settings", config)
    with pytest.raises(SystemExit):
        cli.main(arguments() + ["--period", "2026-13"])
    config.assert_not_called()
