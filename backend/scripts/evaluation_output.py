"""평가 출력 경로를 먼저 선점하고 완료된 사례를 원자적으로 보존한다."""

import asyncio
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class RunOutput:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.latest: dict[str, Any] = {"cases": [], "summary": {}}
        path.parent.mkdir(parents=True, exist_ok=True)
        # exists 검사만으로는 동시 실행 두 개가 같은 유료 결과를 덮어쓸 수 있다.
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({**self.latest, "run_state": "running"}, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def save(self, result: dict[str, Any], state: str) -> None:
        value = {**copy.deepcopy(result), "run_state": state, "output_format_version": 2}
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.latest = value

    async def checkpoint(self, result: dict[str, Any]) -> None:
        pending = asyncio.create_task(asyncio.to_thread(self.save, result, "running"))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            # 쓰기 중 취소되더라도 running 저장이 나중에 중단 상태를 덮어쓰지 않게 한다.
            await pending
            raise

    def stop(self, state: str, error_code: str) -> None:
        # 원문 예외·설정값은 기록하지 않고 마지막 완료 사례와 중단 상태만 보존한다.
        self.save({**self.latest, "run_error": {"code": error_code}}, state)


def technical_exit_code(result: dict[str, Any]) -> int:
    """실행 실패와 사람의 품질 승인 대기를 별개로 판단한다."""
    summary = result.get("summary", {})
    total = summary.get("total", summary.get("total_cases", 0))
    if not total or summary.get("statuses", {}).get("failed", 0):
        return 1
    checks = summary.get("automatic_checks", {})
    if any(item.get("failed", 0) for item in checks.values() if isinstance(item, dict)):
        return 1
    controls = result.get("grader_controls")
    if isinstance(controls, dict) and controls.get("status") == "failed":
        return 1
    for row in result.get("cases", []):
        if row.get("quality") == "judge_error":
            return 1
        for field in ("judge", "diagnostic_judge"):
            judgment = row.get(field)
            if isinstance(judgment, dict) and judgment.get("failure"):
                return 1
    return 0
