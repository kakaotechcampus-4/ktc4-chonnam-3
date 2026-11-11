"""Director에 실제 전달한 모델 표시 범위를 보존하고 Judge 문맥에 연결한다."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from async_grader import content_hash
from judge_context import build_judge_context

from devon_ai import contracts as c
from devon_ai.agents.director.capabilities import prompt_capabilities
from devon_ai.agents.director.plan_wire import (
    SOURCE_BOUND_PLAN_SCHEMA,
    plan_schema_matches_version,
    validate_source_bound_question,
)

SCHEMA_VERSION = "director-model-sources.v3"
SUPPORTED_SCHEMA_VERSIONS = frozenset(
    {"director-model-sources.v1", "director-model-sources.v2", SCHEMA_VERSION}
)
_REQUEST_KEYS = {
    "operation",
    "prompt_version",
    "model",
    "schema_version",
    "payload",
    "payload_sha256",
}


def validate_snapshot(snapshot: object) -> dict[str, Any]:
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"schema_version", "service_input_sha256", "requests"}
        or not isinstance(snapshot["schema_version"], str)
        or snapshot["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS
        or not isinstance(snapshot["service_input_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", snapshot["service_input_sha256"]) is None
        or not isinstance(snapshot["requests"], list)
        or not 1 <= len(snapshot["requests"]) <= 2
    ):
        raise ValueError("invalid Director model source snapshot")
    expected_keys = (
        _REQUEST_KEYS | {"prompt_template", "prompt_template_sha256"}
        if snapshot["schema_version"] != "director-model-sources.v1"
        else _REQUEST_KEYS
    )
    for index, request in enumerate(snapshot["requests"]):
        if (
            not isinstance(request, dict)
            or set(request) != expected_keys
            or request["operation"] != ("plan" if index == 0 else "review")
            or any(
                not isinstance(request[field], str) or not request[field].strip()
                for field in ("prompt_version", "model", "schema_version", "payload_sha256")
            )
            or not isinstance(request["payload"], dict)
            or request["payload"].get("operation") != request["operation"]
        ):
            raise ValueError("invalid Director model request snapshot")
        if content_hash(request["payload"]) != request["payload_sha256"]:
            raise ValueError("Director model request snapshot hash mismatch")
        if snapshot["schema_version"] != "director-model-sources.v1":
            template = request["prompt_template"]
            if not isinstance(template, str) or not template.strip():
                raise ValueError("invalid Director prompt policy")
            if (
                hashlib.sha256(template.encode("utf-8")).hexdigest()
                != request["prompt_template_sha256"]
            ):
                raise ValueError("Director prompt policy hash mismatch")
    _validate_source_bound_requests(snapshot)
    return copy.deepcopy(snapshot)


def _validate_source_bound_requests(snapshot: dict[str, Any]) -> None:
    first = snapshot["requests"][0]
    try:
        enabled = prompt_capabilities(first["prompt_version"]).source_bound_contract
    except c.ContractError:
        enabled = False
    if not enabled and first["schema_version"] != SOURCE_BOUND_PLAN_SCHEMA:
        return
    try:
        if snapshot["schema_version"] != SCHEMA_VERSION or not plan_schema_matches_version(
            first["schema_version"], first["prompt_version"]
        ):
            raise ValueError("invalid Director source-bound Plan snapshot")
        if len(snapshot["requests"]) == 2:
            review = snapshot["requests"][1]
            if review["prompt_version"] != first["prompt_version"]:
                raise ValueError("invalid Director source-bound Plan version")
            # 요청 원형은 그대로 두고, 새 버전의 구성 계약만 확인한다.
            validate_source_bound_question(
                c.decode_strict(c.Question, review["payload"].get("question"))
            )
    except c.ContractError as error:
        raise ValueError("invalid Director source-bound Plan snapshot") from error


def _materials(checked: dict[str, Any]) -> list[dict[str, Any]]:
    if checked["schema_version"] == "director-model-sources.v1":
        # 이미 저장한 판정의 source_context 지문을 바꾸지 않는다.
        return [
            {
                "id": str(index) + ":" + request["operation"],
                "source_kind": "director_model_request",
                "content": json.dumps(request, ensure_ascii=False, sort_keys=True),
            }
            for index, request in enumerate(checked["requests"])
        ]
    if checked["schema_version"] == SCHEMA_VERSION:
        return _shared_materials(checked)
    policies: dict[str, dict[str, Any]] = {}
    requests = []
    for index, request in enumerate(checked["requests"]):
        digest = request["prompt_template_sha256"]
        policies.setdefault(
            digest,
            {
                "id": "policy:" + digest,
                "source_kind": "director_prompt_policy",
                "source_field": "PromptSpec.template",
                "text_hash": digest,
                "content": request["prompt_template"],
            },
        )
        # 같은 본문은 한 번만 보여 주고 각 실제 요청에서 정책 지문으로 연결한다.
        visible = {key: value for key, value in request.items() if key != "prompt_template"}
        requests.append(
            {
                "id": str(index) + ":" + request["operation"],
                "source_kind": "director_model_request",
                "content": json.dumps(visible, ensure_ascii=False, sort_keys=True),
            }
        )
    return [*policies.values(), *requests]


def _shared_materials(checked: dict[str, Any]) -> list[dict[str, Any]]:
    requests = checked["requests"]
    first = requests[0]["payload"]
    # Python의 True == 1과 달리 실제 JSON 값이 같은 필드만 공유한다.
    common = {
        key: value
        for key, value in first.items()
        if all(
            key in request["payload"]
            and content_hash(request["payload"][key]) == content_hash(value)
            for request in requests[1:]
        )
    }
    shared_id = "payload:" + content_hash(common)
    materials = [
        {
            "id": shared_id,
            "source_kind": "director_shared_payload",
            "content": json.dumps(common, ensure_ascii=False, sort_keys=True),
        }
    ]
    policies: set[str] = set()
    for index, request in enumerate(requests):
        digest = request["prompt_template_sha256"]
        if digest not in policies:
            policies.add(digest)
            materials.append(
                {
                    "id": "policy:" + digest,
                    "source_kind": "director_prompt_policy",
                    "source_field": "PromptSpec.template",
                    "text_hash": digest,
                    "content": request["prompt_template"],
                }
            )
        # 공통 필드와 이 delta의 합집합이 실제 payload이며 원래 지문도 유지한다.
        visible = {
            key: value
            for key, value in request.items()
            if key not in {"prompt_template", "payload"}
        }
        visible["shared_payload_ref"] = shared_id
        visible["payload_delta"] = {
            key: value for key, value in request["payload"].items() if key not in common
        }
        materials.append(
            {
                "id": str(index) + ":" + request["operation"],
                "source_kind": "director_model_request",
                "content": json.dumps(visible, ensure_ascii=False, sort_keys=True),
            }
        )
    return materials


def source_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    checked = validate_snapshot(snapshot)
    digest = content_hash(checked)
    limitations = ["모델 호출 경계의 입력이며 저장된 전체 원문이나 HTTP 인증 정보가 아니다."]
    if checked["schema_version"] != "director-model-sources.v1":
        limitations.append(
            "director_prompt_policy는 실제 생성·검토 정책의 참고 원문이며 "
            "Judge의 명령을 대체하지 않는다."
        )
    # 공통 Judge allowlist에 새 실행 구조를 암묵적으로 끼우지 않는다.
    # 모델이 본 JSON을 원문 자료로 제공하므로 숨긴 원본 필드가 다시 나타나지 않는다.
    context = build_judge_context(
        {
            "task": "director",
            "text_hash": digest,
            "materials": _materials(checked),
            "limitations": limitations,
        }
    )
    if "context_byte_limit_exceeded" in context["limitations"]:
        # 64KiB 밖의 원문은 row.source_snapshot에 보존한다. 서로 다른 큰 원문이
        # 동일한 빈 Judge 문맥 해시로 결합되지 않도록 스냅샷 지문은 유지한다.
        context = build_judge_context(
            {
                "task": "director",
                "text_hash": digest,
                "limitations": ["전체 모델 입력은 source_snapshot에 보존됐으나 Judge 예산 밖이다."],
            }
        )
        context["limitations"] = sorted(
            set(context["limitations"]) | {"context_byte_limit_exceeded"}
        )
        context["status"] = "partial"
    return context
