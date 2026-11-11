"""검증된 Review의 사적 진단 기록. 사실 근거나 Judge 입력으로 사용하지 않는다."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any

from async_grader import content_hash
from director_sources import validate_snapshot

from devon_ai import contracts as c
from devon_ai.agents.director.capabilities import prompt_capabilities
from devon_ai.agents.director.plan_wire import SOURCE_BOUND_PLAN_SCHEMA
from devon_ai.agents.director.review import (
    LEGACY_REVIEW_SCHEMA,
    REVIEW_CHECKS,
    SUPPORTED_REVIEW_SCHEMAS,
    assess_review,
    review_schema_version,
)

SCHEMA_VERSION = "director-diagnostics.v2"
LEGACY_SCHEMA_VERSION = "director-diagnostics.v1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION, SCHEMA_VERSION})


def _recovery_from_assessment(assessment: object, request: Mapping[str, Any]) -> str | None:
    try:
        required_points = prompt_capabilities(request["prompt_version"]).required_point_review
        schema_version = review_schema_version(request["prompt_version"])
        if request["schema_version"] != schema_version:
            raise ValueError("invalid Director diagnostic Review version")
        if required_points:
            candidate = c.decode_strict(c.Question, request["payload"].get("question"))
            result = assess_review(assessment, candidate, schema_version)
            return result.recovery if isinstance(result, c.CandidateRecovery) else None
    except c.ContractError as error:
        raise ValueError("invalid Director diagnostic assessment") from error
    # 구형 평가 기록은 기존의 Review 응답과 결과 규칙으로 읽는다.
    if (
        type(assessment) is not dict
        or set(assessment) != {*REVIEW_CHECKS, "reason_summary"}
        or any(type(assessment[key]) is not bool for key in REVIEW_CHECKS)
        or type(assessment["reason_summary"]) is not str
        or not assessment["reason_summary"].strip()
    ):
        raise ValueError("invalid Director diagnostic assessment")
    if all(assessment[key] for key in REVIEW_CHECKS[:-1]):
        return None
    if not assessment["safe_alternative"]:
        return "no_valid_candidate"
    if not assessment["plan_valid"] or not assessment["context_valid"]:
        return "replan"
    return "rewrite"


def validate_diagnostics(
    value: object,
    *,
    service_input_sha256: str,
    source_snapshot: object,
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """v2는 실제 JSON 내용까지 결합한다. v1은 내용 결합 없는 기존 원형 검증만 유지한다."""
    if (
        type(value) is not dict
        or set(value)
        != {"schema_version", "service_input_sha256", "source_snapshot_sha256", "reviews"}
        or type(value["schema_version"]) is not str
        or value["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS
        or value["service_input_sha256"] != service_input_sha256
        or value["source_snapshot_sha256"] != content_hash(source_snapshot)
        or type(value["reviews"]) is not list
        or len(value["reviews"]) != 1
        or not isinstance(attempts, Sequence)
        or any(not isinstance(attempt, Mapping) for attempt in attempts)
    ):
        raise ValueError("invalid Director diagnostics binding")
    try:
        snapshot = validate_snapshot(source_snapshot)
    except ValueError as error:
        raise ValueError("invalid Director diagnostics source binding") from error
    if snapshot["service_input_sha256"] != service_input_sha256:
        raise ValueError("Director diagnostics service binding mismatch")
    if any("canonical_question_sha256" in attempt for attempt in attempts) and (
        snapshot["requests"][0]["schema_version"] != SOURCE_BOUND_PLAN_SCHEMA
    ):
        # 새 원시 형식에서 만든 구성 지문을 구형 정책의 판정으로 재해석하지 않는다.
        raise ValueError("invalid Director diagnostic Plan schema downgrade")
    if snapshot["requests"][0]["schema_version"] == SOURCE_BOUND_PLAN_SCHEMA:
        _validate_plan_question_binding(snapshot, attempts)
    for review in value["reviews"]:
        if (
            type(review) is not dict
            or set(review)
            != {
                "request_index",
                "attempt_index",
                "request_payload_sha256",
                "prompt_version",
                "prompt_template_sha256",
                "response_raw_sha256",
                "response_model",
                "assessment",
                "recovery",
            }
            or type(review["request_index"]) is not int
            or review["request_index"] != 1
            or len(snapshot["requests"]) != 2
            or type(review["attempt_index"]) is not int
            or not 0 <= review["attempt_index"] < len(attempts)
        ):
            raise ValueError("invalid Director diagnostic review")
        request = snapshot["requests"][review["request_index"]]
        attempt = attempts[review["attempt_index"]]
        if (
            request["operation"] != "review"
            or request["schema_version"] not in SUPPORTED_REVIEW_SCHEMAS
            or (
                request["schema_version"] != LEGACY_REVIEW_SCHEMA
                and value["schema_version"] != SCHEMA_VERSION
            )
            or review["request_payload_sha256"] != request["payload_sha256"]
            or review["prompt_version"] != request["prompt_version"]
            or review["prompt_template_sha256"] != request.get("prompt_template_sha256")
            or not isinstance(review["response_raw_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", review["response_raw_sha256"]) is None
            or review["response_raw_sha256"] != attempt.get("raw_output_sha256")
            or (
                value["schema_version"] == SCHEMA_VERSION
                and content_hash(review["assessment"]) != attempt.get("raw_output_json_sha256")
            )
            or type(review["response_model"]) is not str
            or not review["response_model"].strip()
            or review["response_model"] != attempt.get("model")
            or attempt.get("error_stage") is not None
            or attempt.get("error_code") is not None
            or any(attempt.get(key) != request[key] for key in ("prompt_version", "schema_version"))
            or review["recovery"] != _recovery_from_assessment(review["assessment"], request)
        ):
            raise ValueError("Director diagnostic request/response binding mismatch")
    return copy.deepcopy(value)


def _validate_plan_question_binding(
    snapshot: Mapping[str, Any], attempts: Sequence[Mapping[str, Any]]
) -> None:
    # 원문은 실제 시도 기록에 보존하고 평가에는 공유 decoder가 만든 질문의 지문만 결합한다.
    requests = snapshot["requests"]
    if len(requests) != 2 or len(attempts) != 2:
        raise ValueError("invalid Director diagnostic Plan attempts")
    plan = attempts[0]
    request = requests[0]
    question = requests[1]["payload"].get("question")
    if (
        any(plan.get(key) != request[key] for key in ("prompt_version", "schema_version"))
        or plan.get("error_stage") is not None
        or plan.get("error_code") is not None
        or plan.get("canonical_question_sha256") != content_hash(question)
        or any(
            not isinstance(plan.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", plan[key]) is None
            for key in ("raw_output_sha256", "raw_output_json_sha256")
        )
    ):
        raise ValueError("invalid Director diagnostic Plan question binding")
