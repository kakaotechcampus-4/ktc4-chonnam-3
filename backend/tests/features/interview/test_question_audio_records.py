import asyncio
import importlib
from dataclasses import replace
from time import monotonic
from uuid import uuid4

import pytest
from devon_ai.contracts import AttemptMetadata
from sqlalchemy import event, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

from app.db.models import LLMCallRecord, User
from app.features.interview.question_audio import AudioQuestion

from .factories import make_interview, make_repo, make_run, make_turn, make_user


def module():
    return importlib.import_module("app.features.interview.question_audio_records")


def attempt(**overrides):
    return replace(AttemptMetadata(1, "mock", "test-model", "test-v1", "v1", 5, 23, 7), **overrides)


def question():
    return AudioQuestion(uuid4(), 1, uuid4(), "PRIVATE_QUESTION", "tech_lead")


async def test_no_attempts_never_opens_a_database_session():
    def forbidden():
        raise AssertionError("empty metadata must not use the database")

    await module().record_question_pronunciation(forbidden, question(), [])


@pytest.mark.parametrize("error", [SQLAlchemyError, OSError, TimeoutError])
@pytest.mark.parametrize("known_tokens", [True, False])
async def test_optional_record_failure_logs_safe_usage_without_payload(error, known_tokens):
    def unavailable():
        raise error("PRIVATE_DATABASE_URL_AND_PASSWORD")

    attempts = [attempt(raw_output="PRIVATE_PROVIDER_OUTPUT")]
    if not known_tokens:
        attempts.append(attempt(attempt=2, input_tokens=None, output_tokens=None))
    with capture_logs() as logs:
        await module().record_question_pronunciation(unavailable, question(), attempts)
    assert len(logs) == 1
    assert logs[0]["event"] == "question_pronunciation_record_unavailable"
    assert logs[0]["attempt_count"] == len(attempts)
    assert logs[0]["input_tokens"] == (23 if known_tokens else None)
    assert logs[0]["output_tokens"] == (7 if known_tokens else None)
    assert logs[0]["exception_type"] == error.__name__
    assert "PRIVATE_" not in str(logs)


@pytest.fixture
async def records_factory(test_database_url):
    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def stored_question(records_factory):
    async with records_factory() as db:
        run = await make_run(db, await make_user(db))
        interview = await make_interview(db, run, [await make_repo(db, run)], current_turn=1)
        turn = await make_turn(db, interview, 1)
        await db.commit()
        return AudioQuestion(interview.id, 1, turn.id, turn.question_text, turn.persona)


async def records(factory, source):
    async with factory() as db:
        return list(
            (
                await db.scalars(
                    select(LLMCallRecord).where(LLMCallRecord.turn_id == source.turn_id)
                )
            ).all()
        )


async def test_records_metadata_in_own_transaction_without_touching_request_session(
    records_factory, stored_question
):
    async with records_factory() as request_db:
        pending = User(name="request-pending")
        request_db.add(pending)
        await module().record_question_pronunciation(
            records_factory,
            stored_question,
            [attempt(raw_output="PRIVATE_PROVIDER_OUTPUT", response_id="PRIVATE_RESPONSE_ID")],
        )
        assert pending in request_db.new
        assert request_db.in_transaction()
        assert await request_db.scalar(text("SELECT 1")) == 1
        await request_db.rollback()
    saved = await records(records_factory, stored_question)
    assert len(saved) == 1
    assert saved[0].attempts == [
        {
            "attempt": 1,
            "provider": "mock",
            "model": "test-model",
            "prompt_version": "test-v1",
            "schema_version": "v1",
            "latency_ms": 5,
            "input_tokens": 23,
            "output_tokens": 7,
            "error_stage": None,
            "error_code": None,
        }
    ]
    assert saved[0].failure is None


async def test_record_constraint_failure_leaves_request_session_usable(
    records_factory, stored_question
):
    source = replace(stored_question, turn_id=uuid4())
    async with records_factory() as request_db:
        assert await request_db.scalar(text("SELECT 1")) == 1
        with capture_logs() as logs:
            await module().record_question_pronunciation(records_factory, source, [attempt()])
        assert await request_db.scalar(text("SELECT 1")) == 1
    assert len(logs) == 1
    assert await records(records_factory, stored_question) == []


@pytest.fixture
async def slow_commit(records_factory, stored_question):
    name = "record_delay_" + uuid4().hex

    async def install(seconds):
        async with records_factory.begin() as db:
            await db.execute(
                text(
                    f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    f"BEGIN PERFORM pg_sleep({float(seconds)}); RETURN NEW; END $$"
                )
            )
            await db.execute(
                text(
                    f"CREATE CONSTRAINT TRIGGER {name} AFTER INSERT ON llm_call_records "
                    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                    f"WHEN (NEW.turn_id = '{stored_question.turn_id}') "
                    f"EXECUTE FUNCTION {name}()"
                )
            )

    yield install
    async with records_factory.begin() as db:
        await db.execute(text(f"DROP TRIGGER IF EXISTS {name} ON llm_call_records"))
        await db.execute(text(f"DROP FUNCTION IF EXISTS {name}()"))


async def test_commit_slower_than_quarter_second_is_recorded(
    records_factory, stored_question, slow_commit
):
    await slow_commit(0.35)
    await module().record_question_pronunciation(records_factory, stored_question, [attempt()])
    assert len(await records(records_factory, stored_question)) == 1


async def test_slow_commit_timeout_does_not_poison_request_or_persist_record(
    records_factory, stored_question, slow_commit, monkeypatch
):
    import app.integrations.tts.google as finalization

    monkeypatch.setattr(finalization, "FINALIZATION_TIMEOUT_SECONDS", 0.05)
    await slow_commit(2)
    async with records_factory() as request_db:
        assert await request_db.scalar(text("SELECT 1")) == 1
        started = monotonic()
        with capture_logs() as logs:
            await module().record_question_pronunciation(
                records_factory, stored_question, [attempt()]
            )
        assert monotonic() - started < 1.5
        assert await request_db.scalar(text("SELECT 1")) == 1
    assert len(logs) == 1
    assert logs[0]["exception_type"] == "TimeoutError"
    assert await records(records_factory, stored_question) == []


@pytest.mark.parametrize(("delay", "saved_count"), [(0.15, 1), (2, 0)])
async def test_caller_cancellation_finishes_bounded_record_then_propagates(
    records_factory, stored_question, slow_commit, monkeypatch, delay, saved_count
):
    if saved_count == 0:
        import app.integrations.tts.google as finalization

        monkeypatch.setattr(finalization, "FINALIZATION_TIMEOUT_SECONDS", 0.05)
    await slow_commit(delay)
    inserted = asyncio.Event()
    engine = records_factory.kw["bind"]

    def observe_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO llm_call_records"):
            inserted.set()

    event.listen(engine.sync_engine, "after_cursor_execute", observe_insert)
    try:
        task = asyncio.create_task(
            module().record_question_pronunciation(records_factory, stored_question, [attempt()])
        )
        async with asyncio.timeout(2):
            await inserted.wait()
            started = monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert monotonic() - started < 1.5
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", observe_insert)
    assert len(await records(records_factory, stored_question)) == saved_count
