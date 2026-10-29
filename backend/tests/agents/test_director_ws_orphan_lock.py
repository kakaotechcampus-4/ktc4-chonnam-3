"""죽은 소유자의 30초 lock을 실제 TCP WS에서 기다린 뒤 안전하게 연결한다."""

import asyncio
import json
import socket
import threading
import time

import uvicorn
from websockets.asyncio.client import connect

from tests.agents import test_director_ws
from tests.agents.test_director_runtime_service import seed_turns

connect_ws = test_director_ws.connect_ws


async def test_tcp_websocket_waits_for_orphan_lock_without_overwriting_its_owner(
    agent_sessions, agent_seed, connect_ws, record_property
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, app, path, sid, realtime):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        ready = threading.Event()

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                ready.set()

        server = ReadyServer(
            uvicorn.Config(app, lifespan="off", access_log=False, log_level="warning")
        )

        async def serve():
            await server.serve(sockets=[listener])

        serving = client.portal.start_task_soon(serve)
        connecting = None
        connection = None
        try:
            assert await asyncio.to_thread(ready.wait, 5)

            async def dead_owner():
                await app.state.redis.set(f"ws:lock:{realtime}", "dead-owner", ex=30)

            client.portal.call(dead_owner)
            started = time.monotonic()

            async def open_socket():
                return await connect(
                    f"ws://127.0.0.1:{port}{path}",
                    origin="http://localhost:5173",
                    additional_headers={"Cookie": f"devon_session={sid}"},
                    open_timeout=35,
                )

            connecting = asyncio.create_task(open_socket())
            await asyncio.sleep(0.2)

            async def owner():
                return await app.state.redis.get(f"ws:lock:{realtime}")

            assert client.portal.call(owner) == b"dead-owner"
            assert not connecting.done()
            connection = await connecting
            elapsed = time.monotonic() - started
            assert 28 <= elapsed < 35
            event = json.loads(await connection.recv())
            assert event["type"] == "question" and event["turn"] == 1
            assert client.portal.call(owner) != b"dead-owner"
            record_property("handshake_seconds", elapsed)
        finally:
            if connecting is not None and not connecting.done():
                connecting.cancel()
                await asyncio.gather(connecting, return_exceptions=True)
            if connection is not None:
                await connection.close()
            server.should_exit = True
            await asyncio.to_thread(serving.result, 5)
            listener.close()
