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

from async_grader import VERDICTS, GraderLike, call_grader
from director_diagnostics import validate_diagnostics
from director_sources import SUPPORTED_SCHEMA_VERSIONS as DIRECTOR_SOURCES_VERSIONS
from director_sources import source_context as director_source_context
from eval_artifacts import validate_artifacts
from eval_cases import Case
from grader_check import check_grader_async
from judge_context import build_judge_context
from report_check import check_form, grade_reports
from repository_sources import source_context as repository_source_context


@dataclass(frozen=True)
class Execution:
    output: object
    attempts: tuple[dict[str, Any], ...] = ()
    validated_only: bool = False
    artifacts: Mapping[str, object] | None = None
    source_snapshot: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None


class ExecutionError(ValueError):
    """비밀값이나 입력 원문 없이 실패 단계와 코드만 기록한다."""

    def __init__(
        self,
        stage: str,
        code: str,
        attempts: tuple[dict[str, Any], ...] = (),
        *,
        source_snapshot: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self.stage, self.code, self.attempts = stage, code, attempts
        self.source_snapshot = source_snapshot
        self.diagnostics = diagnostics
        super().__init__(code)


Executor = Callable[[str, dict[str, Any]], Awaitable[Execution]]
Checkpoint = Callable[[dict[str, Any]], Awaitable[None]]


async def _checkpoint(
    callback: Checkpoint | None,
    metadata: Mapping[str, object],
    rows: list[dict[str, Any]],
    total: int,
    current: str | None,
    *,
    inflight_case: Mapping[str, Any] | None = None,
) -> None:
    if callback is not None:
        # 이후 rows가 바뀌거나 다음 모델 호출이 중단돼도 완료 원문은 보존한다.
        document: dict[str, Any] = {
            "format_version": 1,
            "metadata": dict(metadata),
            "cases": copy.deepcopy(rows),
            "checkpoint": {"completed": len(rows), "total": total, "current_case": current},
            "summary": {"total": total, "completed": len(rows), "release_gate_passed": None},
        }
        if inflight_case is not None:
            document["inflight_case"] = copy.deepcopy(dict(inflight_case))
        await callback(document)


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


def _source_context(case: Case, row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row.get("source_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict) or row.get("source_snapshot_hash") != _hash(snapshot):
            raise ValueError("rejudge source snapshot hash mismatch")
        if (
            isinstance(snapshot.get("schema_version"), str)
            and snapshot["schema_version"] in DIRECTOR_SOURCES_VERSIONS
        ):
            if (
                case.kind not in {"question", "flow"}
                or case.payload.get("service_task") != "director"
                or snapshot.get("service_input_sha256") != _hash(case.payload)
            ):
                raise ValueError("rejudge Director source snapshot binding mismatch")
            return director_source_context(snapshot)
        if case.kind in {"repo_shallow", "repo_deep"}:
            data = case.model_input()["service_input"]
            declared = data.get("repository", data)
            observed = snapshot.get("repository", {})
            if (
                not isinstance(observed, dict)
                or snapshot.get("task") != case.kind
                or any(
                    observed.get(key) != declared.get(key) for key in ("repository_id", "head_sha")
                )
            ):
                raise ValueError("rejudge source snapshot binding mismatch")
        return repository_source_context(snapshot)
    if row.get("source_snapshot_hash") is not None:
        raise ValueError("rejudge source snapshot missing")
    return build_judge_context(case.model_input())


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
        _source_context(case, row)
        _validate_diagnostics(case, row)
    return indexed


def _validate_diagnostics(case: Case, row: Mapping[str, Any]) -> None:
    value = row.get("diagnostics")
    if value is None:
        if row.get("diagnostics_hash") is not None:
            raise ValueError("rejudge diagnostics missing")
        return
    if case.payload.get("service_task") != "director" or case.kind not in {"question", "flow"}:
        raise ValueError("invalid Director diagnostics case binding")
    if row.get("diagnostics_hash") != _hash(value):
        raise ValueError("rejudge diagnostics hash mismatch")
    validate_diagnostics(
        value,
        service_input_sha256=_hash(case.payload),
        source_snapshot=row.get("source_snapshot"),
        attempts=row.get("attempts", []),
    )


def _preserve_diagnostics(case: Case, row: dict[str, Any], evidence: Any) -> None:
    value = getattr(evidence, "diagnostics", None)
    if value is not None:
        row.update(diagnostics=copy.deepcopy(value), diagnostics_hash=_hash(value))
        _validate_diagnostics(case, {**row, "attempts": list(evidence.attempts)})


def review_packets(
    cases: Sequence[Case],
    previous: Mapping[str, Any],
    *,
    bindings: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, Any]]:
    """재판정과 동일한 후보·원문을 내보내고 숨은 검수·control은 전달하지 않는다."""
    indexed = validate_rejudge_source(cases, previous, bindings=bindings)
    packets = []
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        row = indexed[stem]
        if row["status"] != "succeeded":
            continue
        rubric = {key: copy.deepcopy(case.expectation[key]) for key in ("allowed", "forbidden")}
        candidate = _candidate(row["output"], row.get("artifacts"))
        context = _source_context(case, row)
        packets.append(
            {
                "case": stem,
                "rubric": rubric,
                "candidate_output": candidate,
                "source_context": context,
                "binding": {
                    "rubric_sha256": _hash(rubric),
                    "candidate_sha256": _hash(candidate),
                    "source_context_sha256": _hash(context),
                },
            }
        )
    return packets


async def rejudge_cases(
    cases: Sequence[Case],
    previous: Mapping[str, Any],
    grader: GraderLike,
    *,
    metadata: Mapping[str, object],
    bindings: Mapping[str, Mapping[str, object]] | None = None,
    checkpoint: Checkpoint | None = None,
) -> dict[str, Any]:
    """저장된 성공 출력만 재판정한다. 실패 보존 및 서비스 모델 호출 0을 구조로 보장한다."""
    indexed = validate_rejudge_source(cases, previous, bindings=bindings)
    rows: list[dict[str, Any]] = []
    verdicts: Counter[str] = Counter()
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        await _checkpoint(checkpoint, metadata, rows, len(cases), stem)
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
            "source_snapshot": copy.deepcopy(original.get("source_snapshot")),
            "source_snapshot_hash": original.get("source_snapshot_hash"),
            "attempts": copy.deepcopy(original.get("attempts", [])),
            "diagnostics": copy.deepcopy(original.get("diagnostics")),
            "diagnostics_hash": original.get("diagnostics_hash"),
            "review_status": case.expectation["review"]["status"],
            "status": "not_rejudged",
            "judge": None,
        }
        if original["status"] == "succeeded":
            rubric = {key: case.expectation[key] for key in ("allowed", "forbidden")}
            try:
                judgment = await call_grader(
                    grader,
                    rubric,
                    _candidate(original["output"], original.get("artifacts")),
                    source_context=_source_context(case, original),
                )
            except BaseException as error:
                row.update(
                    status="interrupted",
                    error_stage="interrupted",
                    error_code=type(error).__name__,
                    interrupted_stage="evaluation",
                )
                await _checkpoint(checkpoint, metadata, rows, len(cases), stem, inflight_case=row)
                raise
            row.update(status="rejudged", judge=asdict(judgment))
            verdicts[_diagnostic_verdict(asdict(judgment))] += 1
        rows.append(row)
        await _checkpoint(checkpoint, metadata, rows, len(cases), None)
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
        "input_contract": _check_summary(len(rows), inputs_passed, inputs_failed),
        "service_execution": _check_summary(len(rows), service_passed, service_failed),
        "report_form": _check_summary(len(reports), len(checked_reports) - bad_forms, bad_forms),
        "judge_controls": _check_summary(len(control_rows), controls_passed, controls_failed),
        # Judge가 유효한 reject를 반환해도 실행 자체는 성공이다. 판정별 수는 별도로 남긴다.
        "diagnostic_judge_execution": _check_summary(
            len(candidates), diagnostic_passed, diagnostic_failed
        ),
    }


async def run_cases(
    cases: Sequence[Case],
    executor: Executor,
    *,
    metadata: Mapping[str, object],
    grader: GraderLike | None = None,
    calibration_only: bool = False,
    bindings: Mapping[str, Mapping[str, object]] | None = None,
    diagnostic_judge: bool = False,
    checkpoint: Checkpoint | None = None,
) -> dict[str, Any]:
    """검수 전 실행도 진단 기록으로 남기고 품질 통과와 분모에서는 구분한다."""
    rows: list[dict[str, Any]] = []
    outputs: dict[str, object] = {}
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        await _checkpoint(checkpoint, metadata, rows, len(cases), stem)
        review_status = case.expectation["review"]["status"]
        row: dict[str, Any] = {
            "case": stem,
            "kind": case.kind,
            "split": case.split,
            "source_group_id": case.source_group_id,
            "review_status": review_status,
            "input_hash": _hash(case.payload),
            "expectation_hash": _hash(case.expectation),
            "quality": f"excluded_{review_status}",
            "cost_usd": None,
            "cost_status": "not_configured",
            "attempts": [],
            "output": None,
            "input_tokens": None,
            "output_tokens": None,
            "error_stage": None,
            "error_code": None,
            "input_binding": dict(bindings.get(stem, {})) if bindings else None,
            "judge": None,
            "diagnostic_judge": None,
            "service_latency_ms": 0,
        }
        if review_status == "invalid":
            row.update(status="not_executed", latency_ms=0)
            rows.append(row)
            await _checkpoint(checkpoint, metadata, rows, len(cases), None)
            continue
        if calibration_only:
            binding = bindings.get(stem, {}) if bindings else {}
            row.update(
                status="not_executed",
                latency_ms=0,
                error_stage="input" if binding.get("error_code") else None,
                error_code=binding.get("error_code"),
                execution_scope="judge_controls_only",
            )
            if review_status == "approved":
                row["quality"] = "not_graded"
            rows.append(row)
            await _checkpoint(checkpoint, metadata, rows, len(cases), None)
            continue
        started = time.perf_counter()
        attempts: tuple[dict[str, Any], ...] = ()
        service_completed = False
        try:
            # 실행기는 입력만 받는다. 정답·pair·검수·control 종류를 함께 전달하지 않는다.
            try:
                execution = await executor(case.kind, case.model_input())
            finally:
                # 실패·취소도 사용자가 기다린 서비스 구간이며 Judge 시간은 포함하지 않는다.
                row["service_latency_ms"] = round((time.perf_counter() - started) * 1000)
            service_completed = True
            attempts = execution.attempts
            row.update(
                status="validated_only" if execution.validated_only else "succeeded",
                output=execution.output,
                output_hash=_hash(execution.output),
            )
            if execution.artifacts is not None:
                checked_artifacts = validate_artifacts(dict(execution.artifacts))
                row.update(
                    artifacts=checked_artifacts,
                    artifacts_hash=_hash(checked_artifacts),
                )
            if execution.source_snapshot is not None:
                row.update(
                    source_snapshot=copy.deepcopy(execution.source_snapshot),
                    source_snapshot_hash=_hash(execution.source_snapshot),
                )
                _source_context(case, row)
            _preserve_diagnostics(case, row, execution)
            if not execution.validated_only:
                outputs[stem] = execution.output
            if review_status == "approved":
                row["quality"] = "not_graded"
            if grader is not None and not execution.validated_only:
                if review_status == "approved" or diagnostic_judge:
                    rubric = {
                        key: copy.deepcopy(case.expectation[key])
                        for key in ("allowed", "forbidden")
                    }
                    try:
                        judgment = await call_grader(
                            grader,
                            rubric,
                            _candidate(execution.output, execution.artifacts),
                            source_context=_source_context(case, row),
                        )
                        field = "judge" if review_status == "approved" else "diagnostic_judge"
                        row[field] = asdict(judgment)
                        verdict = judgment.verdict
                        if judgment.failure is not None:
                            raise ValueError("judge execution failed")
                        if verdict not in VERDICTS:
                            raise ValueError("invalid grader verdict")
                        if review_status == "approved":
                            row["quality"] = verdict
                    except Exception:
                        if review_status == "approved":
                            row["quality"] = "judge_error"
                        elif row["diagnostic_judge"] is None:
                            row["diagnostic_judge"] = {
                                "verdict": None,
                                "failure": {
                                    "stage": "judge",
                                    "error_code": "diagnostic_judge_error",
                                },
                            }
        except ExecutionError as exc:
            attempts = exc.attempts
            row.update(status="failed", error_stage=exc.stage, error_code=exc.code)
            if exc.source_snapshot is not None:
                row.update(
                    source_snapshot=copy.deepcopy(exc.source_snapshot),
                    source_snapshot_hash=_hash(exc.source_snapshot),
                )
                _source_context(case, row)
            _preserve_diagnostics(case, row, exc)
            if review_status == "approved":
                row["quality"] = "execution_failed"
        except Exception as exc:
            row.update(status="failed", error_stage="executor", error_code=type(exc).__name__)
            if review_status == "approved":
                row["quality"] = "execution_failed"
        except BaseException as exc:
            if not service_completed:
                attempts = getattr(exc, "attempts", attempts)
                snapshot = getattr(exc, "source_snapshot", None)
                if snapshot is not None:
                    row.update(
                        source_snapshot=copy.deepcopy(snapshot),
                        source_snapshot_hash=_hash(snapshot),
                    )
                _preserve_diagnostics(case, row, exc)
            row.update(
                status="interrupted",
                error_stage="interrupted",
                error_code=type(exc).__name__,
                latency_ms=round((time.perf_counter() - started) * 1000),
                attempts=list(attempts),
                input_tokens=_usage(attempts, "input_tokens"),
                output_tokens=_usage(attempts, "output_tokens"),
                service_status="completed" if service_completed else "interrupted",
                interrupted_stage="evaluation" if service_completed else "service",
            )
            # 취소된 사례는 완료 분모에 넣지 않는다. 이미 생성한 출력·시도·원문과
            # 대기 시간은 별도 미완료 기록으로 남겨 재실행·감사 때 확인할 수 있게 한다.
            await _checkpoint(checkpoint, metadata, rows, len(cases), stem, inflight_case=row)
            raise
        row["attempts"] = list(attempts)
        row["input_tokens"] = _usage(attempts, "input_tokens")
        row["output_tokens"] = _usage(attempts, "output_tokens")
        row["latency_ms"] = round((time.perf_counter() - started) * 1000)
        rows.append(row)
        await _checkpoint(checkpoint, metadata, rows, len(cases), None)
    counts = Counter(row["status"] for row in rows)
    evaluated = {"accept", "reject", "ambiguous", "judge_error", "execution_failed"}
    controls = None
    if grader is not None:
        try:
            controls = await check_grader_async(cases, grader)
        except Exception as exc:
            controls = {"status": "failed", "error_code": type(exc).__name__}
    return {
        "format_version": 1,
        "metadata": dict(metadata),
        "cases": rows,
        "summary": {
            "total": len(rows),
            "statuses": dict(counts),
            "approved_cases": sum(row["review_status"] == "approved" for row in rows),
            "quality_denominator": sum(row["quality"] in evaluated for row in rows),
            "quality_passes": sum(row["quality"] == "accept" for row in rows),
            "automatic_checks": _automatic_checks(rows, controls),
            "diagnostic_verdicts": dict(
                Counter(
                    _diagnostic_verdict(row["diagnostic_judge"])
                    for row in rows
                    if row["diagnostic_judge"] is not None
                )
            ),
            "human_review_status": "deferred",
            "release_gate_passed": None,
            "quality_gate_status": "human_criteria_and_judge_calibration_required",
        },
        "report_checks": grade_reports(cases, outputs, only_approved=True),
        # Judge 자체의 오수락·오거절은 서비스 출력의 판정과 별도 결과로 기록한다.
        "grader_controls": controls,
    }
