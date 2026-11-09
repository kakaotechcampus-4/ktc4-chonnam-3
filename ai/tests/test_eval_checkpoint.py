"""다음 사례가 중단돼도 완료된 출력과 미완료 범위가 남는다."""

import asyncio

import pytest
from eval_cases import Case
from eval_runner import Execution, run_cases


@pytest.mark.asyncio
async def test_completed_cases_are_checkpointed_before_next_executor_can_be_cancelled():
    cases = [
        Case(str(n), 1, "question", "dev", "source", {}, {"review": {"status": "unreviewed"}})
        for n in (1, 2)
    ]
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(value)

    async def execute(kind, payload):
        if any(item.get("cases") for item in checkpoints):
            raise asyncio.CancelledError
        return Execution({"answer": "checked"})

    with pytest.raises(asyncio.CancelledError):
        await run_cases(cases, execute, metadata={}, checkpoint=checkpoint)
    assert checkpoints[-1]["cases"][0]["output"] == {"answer": "checked"}
    assert checkpoints[-1]["checkpoint"] == {"completed": 1, "total": 2, "current_case": "2.v1"}
