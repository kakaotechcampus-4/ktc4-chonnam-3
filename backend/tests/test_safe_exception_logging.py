"""실제 계정 시험의 로그는 예외 원문 대신 종류와 안전한 코드 위치만 남긴다."""

import base64
import io
import json
import logging
import traceback
from uuid import uuid4

import httpx
import pytest
import structlog
from fastapi import FastAPI, Response
from sqlalchemy.exc import StatementError

from app.core.config import Settings
from app.core.logging import configure_logging, get_logger, redact_secrets

SECRET = "synthetic-credential-must-never-be-logged"
SQL = "SELECT private_payload FROM private_account WHERE token=:token"


def _raise_sql_failure():
    raise StatementError(SECRET, SQL, {"token": SECRET}, ValueError(SECRET))


def test_nested_cookie_and_provider_credentials_remain_redacted():
    result = redact_secrets(
        None,
        "warning",
        {"headers": {"Set-Cookie": SECRET}, "STT_API_KEY": SECRET, "error_code": "queue_failed"},
    )
    assert result == {
        "headers": {"Set-Cookie": "[REDACTED]"},
        "STT_API_KEY": "[REDACTED]",
        "error_code": "queue_failed",
    }


@pytest.fixture
def log_output():
    root = logging.getLogger()
    loggers = [root] + [
        item
        for item in logging.Logger.manager.loggerDict.values()
        if isinstance(item, logging.Logger)
    ]
    saved = [(item, item.level, item.filters[:], item.handlers[:]) for item in loggers]
    handlers = {handler for item in loggers for handler in item.handlers}
    handler_state = [(handler, handler.formatter, handler.filters[:]) for handler in handlers]
    configuration = structlog.get_config().copy()
    output = io.StringIO()
    capture = logging.StreamHandler(output)
    root.addHandler(capture)
    try:
        yield output
    finally:
        root.removeHandler(capture)
        capture.close()
        for item, level, filters, previous in saved:
            item.setLevel(level)
            item.filters[:] = filters
            item.handlers[:] = previous
        for handler, formatter, filters in handler_state:
            handler.setFormatter(formatter)
            handler.filters[:] = filters
        structlog.configure(**configuration)


@pytest.mark.parametrize("json_logs", [False, True])
def test_structured_sql_failure_keeps_locations_without_messages_or_locals(log_output, json_logs):
    configure_logging(json_logs=json_logs)
    try:
        _raise_sql_failure()
    except StatementError:
        get_logger("safe-logging-test").warning(
            "operation_failed",
            exc_info=True,
            proxy_token=SECRET,
            sql=SQL,
            nested={"cookie": SECRET, "api_key": SECRET},
        )
    rendered = log_output.getvalue()
    assert SECRET not in rendered
    assert SQL not in rendered
    assert "StatementError" in rendered
    assert "_raise_sql_failure" in rendered
    assert "test_safe_exception_logging.py" in rendered
    assert "Traceback (most recent call last)" not in rendered
    if json_logs:
        record = json.loads(rendered)
        assert record["exception_type"] == "StatementError"
        assert record["exception_frames"][-1]["function"] == "_raise_sql_failure"
        assert record["exception_frames"][-1]["line"] > 0
        assert set(record["exception_frames"][-1]) == {"file", "function", "line"}


@pytest.mark.parametrize("json_logs", [False, True])
def test_standard_arq_exception_removes_exception_argument_and_raw_extra(log_output, json_logs):
    target = logging.getLogger("arq.worker")
    handler = logging.StreamHandler(log_output)
    # CLI가 먼저 설치한 자체 handler에도 같은 정책이 적용돼야 한다.
    handler.setFormatter(logging.Formatter("%(message)s %(exc_text)s"))
    target.addHandler(handler)
    propagate = target.propagate
    target.propagate = False
    try:
        configure_logging(json_logs=json_logs)
        try:
            _raise_sql_failure()
        except StatementError as error:
            # ARQ는 실제로 예외 객체를 메시지 인자에도 넣는다.
            target.exception(
                "job failed, %s: %s", type(error).__name__, error, extra={"extra": {"sql": SQL}}
            )
    finally:
        target.removeHandler(handler)
        target.propagate = propagate
        handler.close()
    rendered = log_output.getvalue()
    assert SECRET not in rendered
    assert SQL not in rendered
    assert "StatementError" in rendered
    assert "_raise_sql_failure" in rendered
    if json_logs:
        record = json.loads(rendered)
        assert record["logger"] == "arq.worker"
        assert record["exception_type"] == "StatementError"
        assert "extra" not in record


def _settings():
    return Settings(
        _env_file=None,
        log_json=True,
        database_url="postgresql+asyncpg://devon:devon@127.0.0.1:9/unconnected",
        redis_url="redis://127.0.0.1:9/0",
        github_client_id="synthetic-client",
        github_client_secret="synthetic-secret",
        token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
    )


@pytest.mark.parametrize("json_logs", [False, True])
@pytest.mark.parametrize("as_argument", [False, True])
def test_preformatted_standard_traceback_does_not_reveal_messages_or_source(
    log_output, json_logs, as_argument
):
    configure_logging(json_logs=json_logs)
    try:
        _raise_sql_failure()
    except StatementError:
        rendered = traceback.format_exc()
    target = logging.getLogger("arq.worker")
    if as_argument:
        target.error("job failed: %s", rendered)
    else:
        target.error(rendered)
    output = log_output.getvalue()
    assert SECRET not in output and SQL not in output
    assert "Traceback (most recent call last)" not in output
    assert "Application exception" in output


async def test_worker_startup_initializes_safe_json_logging_without_database_calls(
    log_output, monkeypatch
):
    from app.workers import arq_app

    monkeypatch.setattr(arq_app, "get_settings", _settings)
    context = {}
    try:
        await arq_app.startup(context)
        get_logger("worker-startup-test").warning("worker_probe")
        assert log_output.getvalue().strip().startswith("{"), "worker must initialize JSON logs"
        assert json.loads(log_output.getvalue())["event"] == "worker_probe"
    finally:
        if "engine" in context:
            await arq_app.shutdown(context)


async def test_api_startup_honors_json_logging_in_local_environment(log_output):
    from app.main import create_app

    application = create_app(_settings())
    async with application.router.lifespan_context(application):
        get_logger("api-startup-test").warning("api_probe")
        assert log_output.getvalue().strip().startswith("{"), "local API must honor LOG_JSON"
        assert json.loads(log_output.getvalue())["event"] == "api_probe"


def _http_records(output):
    return [
        value
        for line in output.getvalue().splitlines()
        if (value := json.loads(line)).get("event") == "http_request"
    ]


@pytest.mark.parametrize("status_code", [200, 403, 500])
async def test_http_result_records_fixed_route_status_latency_and_request_id(
    log_output, status_code
):
    from app.core.logging import RequestIdMiddleware

    configure_logging(json_logs=True)
    application = FastAPI()

    @application.post("/items/{item_id}")
    async def result(item_id: str):
        return Response(SECRET, status_code=status_code)

    identity = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=RequestIdMiddleware(application)), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/items/{SECRET}?code={SECRET}",
            content=SECRET,
            headers={"X-Request-ID": identity, "Authorization": SECRET, "Cookie": SECRET},
        )
    records = _http_records(log_output)
    assert len(records) == 1
    assert records[0]["route"] == "/items/{item_id}"
    assert records[0]["method"] == "POST"
    assert records[0]["status_code"] == status_code
    assert records[0]["request_id"] == identity == response.headers["X-Request-ID"]
    assert isinstance(records[0]["latency_ms"], (int, float))
    assert records[0]["latency_ms"] >= 0
    assert SECRET not in log_output.getvalue()
    assert "request_id" not in structlog.contextvars.get_contextvars()


async def test_oauth_callback_and_unmatched_request_never_log_their_raw_url(log_output):
    from app.core.logging import RequestIdMiddleware

    configure_logging(json_logs=True)
    application = FastAPI()

    @application.get("/api/auth/github/callback")
    async def callback():
        return Response(status_code=302)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=RequestIdMiddleware(application)), base_url="http://test"
    ) as client:
        await client.get(f"/api/auth/github/callback?code={SECRET}&state={SECRET}")
        await client.get(f"/not-found-{SECRET}?token={SECRET}")
    records = _http_records(log_output)
    assert [(record["route"], record["status_code"]) for record in records] == [
        ("/api/auth/github/callback", 302),
        ("unmatched", 404),
    ]
    assert SECRET not in log_output.getvalue()


async def test_unhandled_http_exception_records_500_and_is_not_swallowed(log_output):
    from app.core.logging import RequestIdMiddleware

    configure_logging(json_logs=True)
    application = FastAPI()
    original = RuntimeError(SECRET)

    @application.get("/failure/{item_id}")
    async def failure(item_id: str):
        raise original

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=RequestIdMiddleware(application)), base_url="http://test"
    ) as client:
        with pytest.raises(RuntimeError) as raised:
            await client.get(f"/failure/{SECRET}")
    assert raised.value is original
    assert _http_records(log_output)[0]["status_code"] == 500
    assert _http_records(log_output)[0]["route"] == "/failure/{item_id}"
    assert SECRET not in log_output.getvalue()
    assert "request_id" not in structlog.contextvars.get_contextvars()


async def test_health_requests_are_excluded_by_the_fixed_route_template(log_output):
    from app.core.logging import RequestIdMiddleware

    configure_logging(json_logs=True)
    application = FastAPI()

    @application.get("/api/health")
    async def health():
        return {"status": "ok"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=RequestIdMiddleware(application)), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert _http_records(log_output) == []


async def test_unknown_http_method_is_replaced_with_a_fixed_value(log_output):
    from app.core.logging import RequestIdMiddleware

    configure_logging(json_logs=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=RequestIdMiddleware(FastAPI())), base_url="http://test"
    ) as client:
        await client.request("SECRET-METHOD", f"/{SECRET}")
    assert _http_records(log_output)[0]["method"] == "OTHER"
    assert "SECRET-METHOD" not in log_output.getvalue()
    assert SECRET not in log_output.getvalue()
