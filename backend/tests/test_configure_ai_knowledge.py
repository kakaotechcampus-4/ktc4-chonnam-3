"""개발용 초안 활성화는 명시된 대상만 바꾸고 기존 기준을 보존한다."""

import asyncio
import importlib
import importlib.util
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.knowledge import DomainQuestionFrame, ScoreCriterion
from scripts.seed_domain_question_frames import DOMAIN_QUESTION_FRAMES
from scripts.seed_score_criteria import SCORE_CRITERIA


def module():
    assert importlib.util.find_spec("scripts.configure_ai_knowledge") is not None, (
        "explicit development knowledge configuration is missing"
    )
    return importlib.import_module("scripts.configure_ai_knowledge")


def settings(url="postgresql+asyncpg://devon:private-fixture@localhost:5432/devon", env="local"):
    return SimpleNamespace(database_url=url, app_env=env)


def target(**updates):
    values = dict(profile="development", host="localhost", port=5432, database="devon")
    return module().KnowledgeTarget(**{**values, **updates})


def test_explicit_development_database_does_not_need_a_test_suffix():
    result = module().validate_target(settings(), target(), allow_unreviewed=True)
    assert result["profile"] == "development"
    assert result["environment"] == "local"
    assert result["approval_status"] == "unreviewed"
    assert len(result["target_sha256"]) == 64
    assert "private-fixture" not in str(result)


@pytest.mark.parametrize(
    "config, changes, allow",
    [
        (settings(env="prod"), {}, True),
        (settings(), {}, False),
        (settings(), {"database": "other"}, True),
        (settings(), {"host": "other-host"}, True),
        (settings(), {"port": 9999}, True),
        (settings(), {"profile": "test"}, True),
        (
            settings("postgresql+asyncpg://devon:private-fixture@localhost/postgres"),
            {"database": "postgres"},
            True,
        ),
    ],
)
def test_target_guard_rejects_implicit_wrong_or_production_targets(config, changes, allow):
    with pytest.raises(module().KnowledgeConfigurationError) as error:
        module().validate_target(config, target(**changes), allow_unreviewed=allow)
    assert "private-fixture" not in str(error.value)


def test_cli_requires_an_audit_destination_before_any_database_activation(tmp_path, monkeypatch):
    command = module()
    monkeypatch.setattr(command, "Settings", lambda **kwargs: settings())
    invoked = []

    async def configure(*args, **kwargs):
        invoked.append(kwargs)
        return {"mode": "applied", "approval_status": "unreviewed"}

    monkeypatch.setattr(command, "configure_knowledge", configure)
    output = tmp_path / "audit.json"
    output.write_text("preserve old audit", encoding="utf-8")
    assert (
        command.main(
            [
                "--profile",
                "development",
                "--target-host",
                "localhost",
                "--target-port",
                "5432",
                "--target-database",
                "devon",
                "--allow-unreviewed-drafts",
                "--actor",
                "fixture",
                "--output",
                str(output),
                "--apply",
            ]
        )
        == 1
    )
    assert invoked == []
    assert output.read_text(encoding="utf-8") == "preserve old audit"


def test_cli_defaults_to_dry_run_and_preserves_the_unreviewed_audit(tmp_path, monkeypatch):
    command = module()
    monkeypatch.setattr(command, "Settings", lambda **kwargs: settings())
    invoked = []

    async def configure(*args, **kwargs):
        invoked.append(kwargs["apply"])
        return {"mode": "dry_run", "approval_status": "unreviewed"}

    monkeypatch.setattr(command, "configure_knowledge", configure)
    output = tmp_path / "new-audit.json"
    assert (
        command.main(
            [
                "--profile",
                "development",
                "--target-host",
                "localhost",
                "--target-port",
                "5432",
                "--target-database",
                "devon",
                "--allow-unreviewed-drafts",
                "--actor",
                "fixture",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert invoked == [False]
    assert json.loads(output.read_text(encoding="utf-8"))["approval_status"] == "unreviewed"


@pytest_asyncio.fixture
async def knowledge_database(test_database_url):
    from sqlalchemy.engine import make_url

    engine = create_async_engine(test_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as db:
        await db.execute(delete(ScoreCriterion))
        await db.execute(delete(DomainQuestionFrame))
    url = make_url(test_database_url)
    yield (
        sessions,
        settings(test_database_url),
        module().KnowledgeTarget("test", url.host, url.port or 5432, url.database),
    )
    await engine.dispose()


async def test_dry_run_describes_missing_rows_without_changing_database(knowledge_database):
    sessions, config, selected = knowledge_database
    result = await module().configure_knowledge(
        sessions, config, selected, allow_unreviewed=True, actor="functional-test"
    )
    assert result["mode"] == "dry_run"
    assert result["score_keys"] == sorted(item.score_key for item in SCORE_CRITERIA)
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ScoreCriterion)) == 0
        assert await db.scalar(select(func.count()).select_from(DomainQuestionFrame)) == 0


async def test_apply_registers_exact_drafts_and_is_idempotent_without_human_approval(
    knowledge_database,
):
    sessions, config, selected = knowledge_database
    first = await module().configure_knowledge(
        sessions, config, selected, allow_unreviewed=True, actor="functional-test", apply=True
    )
    second = await module().configure_knowledge(
        sessions, config, selected, allow_unreviewed=True, actor="functional-test", apply=True
    )
    assert first["approval_status"] == second["approval_status"] == "unreviewed"
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert second["changes"] == 0
    async with sessions() as db:
        assert await db.scalar(
            select(func.count()).select_from(ScoreCriterion).where(ScoreCriterion.is_active)
        ) == len(SCORE_CRITERIA)
        assert await db.scalar(
            select(func.count())
            .select_from(DomainQuestionFrame)
            .where(DomainQuestionFrame.is_active)
        ) == len(DOMAIN_QUESTION_FRAMES)


@pytest.mark.parametrize("active", [True, False])
async def test_conflicting_active_rubric_is_preserved_and_frames_are_not_inserted(
    knowledge_database,
    active,
):
    sessions, config, selected = knowledge_database
    async with sessions.begin() as db:
        db.add(
            ScoreCriterion(
                score_key=SCORE_CRITERIA[0].score_key,
                label_ko="existing",
                description="existing",
                rubric={"0": "preserve me"},
                display_order=1,
                is_active=active,
            )
        )
    with pytest.raises(module().KnowledgeConfigurationError):
        await module().configure_knowledge(
            sessions, config, selected, allow_unreviewed=True, actor="functional-test", apply=True
        )
    async with sessions() as db:
        row = await db.scalar(select(ScoreCriterion))
        assert row.rubric == {"0": "preserve me"} and row.is_active == active
        assert await db.scalar(select(func.count()).select_from(DomainQuestionFrame)) == 0


async def test_concurrent_initializers_activate_the_same_bundle_once(knowledge_database):
    sessions, config, selected = knowledge_database
    results = await asyncio.gather(
        *(
            module().configure_knowledge(
                sessions,
                config,
                selected,
                allow_unreviewed=True,
                actor="functional-test",
                apply=True,
            )
            for _ in range(2)
        )
    )
    assert sorted(result["changes"] for result in results) == [
        0,
        len(SCORE_CRITERIA) + len(DOMAIN_QUESTION_FRAMES),
    ]


async def test_database_failure_rolls_back_both_knowledge_tables(knowledge_database):
    sessions, config, selected = knowledge_database
    engine = sessions.kw["bind"].sync_engine

    def fail_score_insert(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO score_criteria" in statement:
            raise RuntimeError("isolated failure after domain inserts")

    event.listen(engine, "before_cursor_execute", fail_score_insert)
    try:
        with pytest.raises(RuntimeError, match="isolated failure"):
            await module().configure_knowledge(
                sessions,
                config,
                selected,
                allow_unreviewed=True,
                actor="functional-test",
                apply=True,
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail_score_insert)
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ScoreCriterion)) == 0
        assert await db.scalar(select(func.count()).select_from(DomainQuestionFrame)) == 0
