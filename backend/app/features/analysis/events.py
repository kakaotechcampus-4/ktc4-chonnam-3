"""SSE 스트림의 구현 예정 경계.
Redis pub/sub 구독 성립 확인 후 Postgres 현재 상태를 전송하고 후속 이벤트를 전달한다.
DB commit 뒤 알리며 중복 상태 제거와 Postgres 재확인으로 알림 유실을 보완한다.

docs/pipeline.md 3절 / task-12

★ PUBLISH payload 모양은 이 파일이 아니라 emit()(task-11 analysis_run worker)이 정한다.
  여기서는 pipeline.md 2절 예시(`{"type":"completed"}`, `{"type":"failed","reason":...}`)와
  step 이벤트는 `{"type":"step","step":...,"status":...}` 라고 가정했다 — task-11 과
  실제 emit() 구현 시 이 형태를 맞춰야 한다(PENDING_TEAM).
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.realtime.bus import RedisEventBus
from app.shared.enums import RunStatus, to_run_status

# Pub/Sub 은 at-most-once 라 구독 이후에도 유실될 수 있다. 종료 상태를 확인할 때까지
# 이 주기로 Postgres 를 재확인해 유실을 보완한다(docs/pipeline.md 3절).
POLL_FALLBACK_SECONDS = 5.0
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "partial", "failed", "canceled"})


@dataclass(frozen=True, slots=True)
class StepState:
    """analysis_jobs.steps 의 한 항목."""

    step: str
    status: str


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """현재 run 상태. Postgres 조회 결과 — 호출부(task-11 analysis/queries.py)가 만든다."""

    status: str
    steps: tuple[StepState, ...]


# 호출부(task-11)가 analysis_jobs 를 읽어 넘겨주는 콜백. 이 모듈은 DB 를 모른다.
ReadSnapshot = Callable[[], Awaitable[RunSnapshot]]


async def stream_run_progress(
    run_id: str,
    *,
    bus: RedisEventBus,
    read_snapshot: ReadSnapshot,
) -> AsyncIterator[dict[str, Any]]:
    """SSE data payload 스트림을 만든다. realtime/sse.py 의 EventSourceResponse 가 감싼다.

    입력: runId, RedisEventBus, 현재 상태를 읽는 콜백. 출력: SSE 이벤트(dict) 스트림.

    ⚠ 순서 고정 — `run:{runId}:events` 구독이 성립한 뒤에 Postgres 현재 상태를 읽는다.
    반대로 하면 스냅샷과 구독 사이에 run 이 끝났을 때 completed 를 영영 못 받는다.
    step 단위 중복은 (step, status) 로 걸러 한 번만 내보낸다.
    """
    seen: set[tuple[str, str]] = set()

    async with bus.subscribe(f"run:{run_id}:events") as subscription:
        snapshot = await read_snapshot()
        for step in snapshot.steps:
            key = (step.step, step.status)
            if key not in seen:
                seen.add(key)
                yield _step_event(step)

        if snapshot.status in TERMINAL_JOB_STATUSES:
            yield _terminal_event(snapshot.status)
            return

        while True:
            message = await subscription.get_message(
                ignore_subscribe_messages=True, timeout=POLL_FALLBACK_SECONDS
            )
            if message is None:
                # 이 주기 동안 메시지가 없었다 — publish 유실에 대비해 Postgres 를 재확인한다.
                snapshot = await read_snapshot()
                if snapshot.status in TERMINAL_JOB_STATUSES:
                    yield _terminal_event(snapshot.status)
                    return
                continue

            event = _handle_message(message, seen)
            if event is None:
                continue
            yield event
            if event["event"] in ("completed", "failed"):
                return


def _handle_message(message: dict[str, Any], seen: set[tuple[str, str]]) -> dict[str, Any] | None:
    """publish 된 메시지 하나를 SSE 이벤트로 바꾼다. 중복 step 이벤트는 None 을 돌려준다."""
    payload = json.loads(message["data"])
    payload_type = payload.get("type")

    if payload_type == "completed":
        return {"event": "completed", "data": json.dumps({"status": "succeeded"})}
    if payload_type == "failed":
        return {
            "event": "failed",
            "data": json.dumps({"status": "failed", "reason": payload.get("reason")}),
        }

    key = (payload["step"], payload["status"])
    if key in seen:
        return None
    seen.add(key)
    return _step_event(StepState(step=payload["step"], status=payload["status"]))


def _step_event(step: StepState) -> dict[str, Any]:
    return {"event": "step", "data": json.dumps({"step": step.step, "status": step.status})}


def _terminal_event(job_status: str) -> dict[str, Any]:
    run_status = to_run_status(job_status)
    event_type = "completed" if run_status is RunStatus.COMPLETED else "failed"
    return {"event": event_type, "data": json.dumps({"status": job_status})}
