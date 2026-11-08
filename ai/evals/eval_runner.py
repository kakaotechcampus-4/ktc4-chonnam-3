"""서비스 실행과 평가를 분리한 로컬 실행기. 런타임 모듈은 가져오지 않는다."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast

from async_grader import GraderLike, call_grader
from eval_artifacts import validate_artifacts
from eval_cases import Case
from grader_check import VERDICTS, check_grader_async
from judge_context import build_judge_context
from report_check import check_form, grade_reports


@dataclass(frozen=True)
class Execution:
    output: object
    attempts: tuple[dict[str, Any], ...] = ()
    validated_only: bool = False
    artifacts: Mapping[str, object] | None = None


class ExecutionError(ValueError):
    """비밀값이나 입력 원문 없이 실패 단계와 코드만 기록한다."""

    def __init__(self, stage: str, code: str, attempts: tuple[dict[str, Any], ...] = ()) -> None:
        self.stage, self.code, self.attempts = stage, code, attempts
        super().__init__(code)


Executor = Callable[[str, dict[str, Any]], Awaitable[Execution]]


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate(output: object, artifacts: object) -> str:
    # 검증된 내부 관찰을 공개 응답에 덧쓰지 않고 별도 평가 입력으로 연결한다.
    value = (
        output
        if artifacts is None
        else {"public_output": output, "validated_artifacts": validate_artifacts(artifacts)}
    )
    return json.dumps(value, ensure_ascii=False)


def validate_rejudge_source(
    cases: Sequence[Case],
    previous: Mapping[str, Any],
    *,
    bindings: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, dict[str, Any]]:
    """기존 실행의 입력·정답·출력을 검증한 뒤에만 Judge 재실행을 허용한다."""
    rows = previous.get("cases")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid rejudge source rows")
    indexed = {row.get("case"): row for row in rows}
    expected = {f"{case.case_id}.v{case.version}" for case in cases}
    if len(indexed) != len(rows) or set(indexed) != expected:
        raise ValueError("rejudge case set mismatch")
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        row = indexed[stem]
        if row.get("status") not in {"succeeded", "failed", "validated_only", "not_executed"}:
            raise ValueError("invalid rejudge original status")
        if row.get("input_hash") != _hash(case.payload) or row.get("expectation_hash") != _hash(
            case.expectation
        ):
            raise ValueError("rejudge case hash mismatch")
        if (row.get("kind"), row.get("split"), row.get("source_group_id")) != (
            case.kind,
            case.split,
            case.source_group_id,
        ):
            raise ValueError("rejudge source binding mismatch")
        if bindings is not None and row.get("input_binding") != dict(bindings.get(stem, {})):
            raise ValueError("rejudge service binding mismatch")
        if row.get("status") == "succeeded" and (
            row.get("output") is None or row.get("output_hash") != _hash(row.get("output"))
        ):
            raise ValueError("rejudge output hash mismatch")
        artifacts, artifact_hash = row.get("artifacts"), row.get("artifacts_hash")
        if artifacts is None:
            if artifact_hash is not None:
                raise ValueError("rejudge artifacts hash mismatch")
        else:
            validate_artifacts(artifacts)
            if artifact_hash != _hash(artifacts):
                raise ValueError("rejudge artifacts hash mismatch")
    return indexed


async def rejudge_cases(
    cases: Sequence[Case],
    previous: Mapping[str, Any],
    grader: GraderLike,
    *,
    metadata: Mapping[str, object],
    bindings: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """저장된 성공 출력만 재판정한다. 실패 보존 및 서비스 모델 호출 0을 구조로 보장한다."""
    indexed = validate_rejudge_source(cases, previous, bindings=bindings)
    rows = []
    verdicts: Counter[str] = Counter()
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        original = indexed[stem]
        row: dict[str, Any] = {
            "case": stem,
            "input_hash": original["input_hash"],
            "expectation_hash": original["expectation_hash"],
            "input_binding": copy.deepcopy(original.get("input_binding")),
            "original_service_status": original["status"],
            "original_error_code": original.get("error_code"),
            "output": copy.deepcopy(original.get("output")),
            "output_hash": original.get("output_hash"),
            "artifacts": copy.deepcopy(original.get("artifacts")),
            "artifacts_hash": original.get("artifacts_hash"),
            "review_status": case.expectation["review"]["status"],
            "status": "not_rejudged",
            "judge": None,
        }
        if original["status"] == "succeeded":
            rubric = {key: case.expectation[key] for key in ("allowed", "forbidden")}
            judgment = await call_grader(
                grader,
                rubric,
                _candidate(original["output"], original.get("artifacts")),
                source_context=build_judge_context(case.model_input()),
            )
            row.update(status="rejudged", judge=asdict(judgment))
            verdicts[_diagnostic_verdict(asdict(judgment))] += 1
        rows.append(row)
    return {
        "format_version": 2,
        "metadata": {**metadata, "execution_scope": "rejudge_existing_outputs"},
        "cases": rows,
        "summary": {
            "total_cases": len(cases),
            "rejudged_outputs": sum(row["status"] == "rejudged" for row in rows),
            "preserved_non_successful_cases": sum(row["status"] != "rejudged" for row in rows),
            "verdicts": dict(verdicts),
            "service_model_calls": 0,
            "human_review_status": "deferred",
            "release_gate_passed": None,
            "original_service_summary": copy.deepcopy(previous.get("summary")),
        },
    }


def _usage(attempts: tuple[dict[str, Any], ...], key: str) -> int | None:
    values = [item.get(key) for item in attempts]
    return (
        sum(cast(int, value) for value in values)
        if values and all(type(value) is int for value in values)
        else None
    )


def _check_summary(total: int, passed: int, failed: int) -> dict[str, Any]:
    """자동 검사의 실제 분모를 남긴다. 미실행을 통과로 채우지 않는다."""
    status = (
        "passed"
        if total and passed == total
        else "partial"
        if passed
        else "failed"
        if failed
        else "not_executed"
    )
    return dict(
        status=status,
        total=total,
        passed=passed,
        failed=failed,
        not_executed=total - passed - failed,
    )


def _diagnostic_verdict(judgment: Mapping[str, Any]) -> str:
    failure = judgment.get("failure")
    if failure:
        return (
            "not_executed"
            if failure.get("error_code") == "evaluation_budget_exhausted"
            else "error"
        )
    verdict = judgment.get("verdict")
    return verdict if type(verdict) is str and verdict in VERDICTS else "error"


def _automatic_checks(
    rows: Sequence[Mapping[str, Any]], controls: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs_passed = inputs_failed = service_passed = service_failed = 0
    for row in rows:
        if row["review_status"] == "invalid" or row.get("execution_scope") == "judge_controls_only":
            continue
        if row["error_stage"] == "input":
            inputs_failed += 1
        elif row["status"] in {"succeeded", "validated_only"} or (
            row["status"] == "failed" and row["error_stage"] != "configuration"
        ):
            inputs_passed += 1
        if row["status"] == "succeeded":
            service_passed += 1
        elif row["status"] == "failed" and row["error_stage"] not in {
            "input",
            "configuration",
            "budget",
        }:
            service_failed += 1
    reports = [row for row in rows if row["kind"] == "report"]
    checked_reports = [row for row in reports if row["status"] == "succeeded"]
    bad_forms = sum(bool(check_form(row["output"])) for row in checked_reports)
    control_rows = controls.get("controls", []) if controls else []
    controls_passed = controls_failed = 0
    for control in control_rows:
        judgment = control["judge"]
        failure = judgment.get("failure")
        if failure and failure.get("error_code") == "evaluation_budget_exhausted":
            continue
        if not failure and judgment.get("verdict") == control["expected_verdict"]:
            controls_passed += 1
        else:
            controls_failed += 1
    candidates = [row for row in rows if row["review_status"] not in {"approved", "invalid"}]
    judgments = [row["diagnostic_judge"] for row in candidates if row["diagnostic_judge"]]
    diagnostic_failed = sum(_diagnostic_verdict(item) == "error" for item in judgments)
    diagnostic_passed = sum(_diagnostic_verdict(item) in VERDICTS for item in judgments)
    return {
