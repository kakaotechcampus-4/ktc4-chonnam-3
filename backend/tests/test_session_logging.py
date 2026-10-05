"""The real ASGI server must not log values from unexpected exceptions."""

import asyncio
import logging
import socket

import httpx
import uvicorn
from fastapi import FastAPI

from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging


async def test_unhandled_exception_keeps_safe_response_and_server_log(caplog):
    configure_logging()
    caplog.set_level(logging.ERROR, logger="uvicorn.error")
    application = FastAPI()
    register_exception_handlers(application)
    secret = "sentinel-provider-credential-do-not-log"

    @application.get("/failure")
    async def failure():
        raise RuntimeError(secret)

    server = uvicorn.Server(
        uvicorn.Config(application, lifespan="off", log_config=None, access_log=False)
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        running = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if running.done():
                        await running
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://127.0.0.1:{port}/failure")
        finally:
            server.should_exit = True
            await asyncio.wait_for(running, timeout=5)

    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
    assert secret not in response.text
    server_errors = [
        record
        for record in caplog.records
        if record.name == "uvicorn.error" and record.levelno >= logging.ERROR
    ]
    assert secret not in caplog.text
    assert any("RuntimeError" in record.getMessage() for record in server_errors)
