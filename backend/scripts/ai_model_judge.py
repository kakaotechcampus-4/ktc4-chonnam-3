"""명시적으로 주입한 공통 gateway와 별도 예산만 사용하는 로컬 평가 Judge."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import Any

from async_grader import Judgment, content_hash
from devon_ai import contracts as c
from judge_context import validate_judge_context


class ModelJudge:
    def __init__(
        self,
        prompt: c.PromptSpec,
        limits: c.CallLimits,
        model_call_factory: Callable[[], Any],
        *,
        sensitive_values: Sequence[str] = (),
    ) -> None:
        if prompt.task_name != "evaluation_judge":
            raise ValueError("evaluation_judge prompt required")
        self.prompt, self.limits, self.factory = prompt, limits, model_call_factory
        self._sensitive = tuple(value for value in sensitive_values if value)
        self.records: list[dict[str, Any]] = []

    def _secret(self, value: object) -> bool:
        encoded = json.dumps(value, ensure_ascii=False)
        return any(secret in encoded for secret in self._sensitive)

    async def __call__(self, rubric: dict[str, Any], output: str) -> Judgment:
        return await self._evaluate(rubric, output)

    async def judge_with_context(
        self, rubric: dict[str, Any], output: str, source_context: object
    ) -> Judgment:
        return await self._evaluate(rubric, output, source_context=source_context)

    async def _evaluate(
        self, rubric: dict[str, Any], output: str, *, source_context: object = None
    ) -> Judgment:
        started = time.monotonic()
        visible = {key: copy.deepcopy(rubric[key]) for key in ("allowed", "forbidden")}
        payload: dict[str, object] = {"rubric": visible, "candidate_output": output}
        metadata: dict[str, Any] = {
            "request_input_sha256": content_hash(payload),
            "prompt_version": self.prompt.version,
            "prompt_template_sha256": hashlib.sha256(self.prompt.template.encode()).hexdigest(),
            "requested_model": self.prompt.model,
            "schema_version": "1",
            "judge_output_sha256": None,
        }

        def finish(result: Judgment) -> Judgment:
            result.metadata["latency_ms"] = round((time.monotonic() - started) * 1000)
            self.records.append(asdict(result))
            return result

        if source_context is not None:
            try:
                checked = validate_judge_context(source_context)
            except ValueError:
                return finish(
                    Judgment(
                        None,
                        failure={"stage": "input", "error_code": "judge_source_context_invalid"},
                        metadata=metadata,
                    )
                )
            payload["source_context"] = checked
            metadata.update(
                request_input_sha256=content_hash(payload),
                source_context_sha256=content_hash(checked),
                source_context_version=checked["schema_version"],
                source_context_status=checked["status"],
            )

        if self._secret(payload) or self._secret(self.prompt.template):
            return finish(
                Judgment(
                    None,
                    failure={
                        "stage": "input",
                        "error_code": "judge_input_contains_configuration_secret",
                    },
                    metadata=metadata,
                )
            )
        identifiers = []
        for group, entries in visible.items():
            for index, criterion in enumerate(entries):
                identifier = criterion.get("id") if isinstance(criterion, dict) else None
                key = (
                    identifier if isinstance(identifier, str) and identifier.strip() else str(index)
                )
                identifiers.append(f"{group}:{key}")
        if not identifiers or len(set(identifiers)) != len(identifiers):
            return finish(
                Judgment(
                    None,
                    failure={"stage": "input", "error_code": "judge_rubric_identity_invalid"},
                    metadata=metadata,
                )
            )
        properties = {
            "verdict": {"type": "string", "enum": ["accept", "reject", "ambiguous"]},
            "reason_summary": {"type": "string"},
            "criterion_results": {
                "type": "array",
                "maxItems": len(identifiers),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": identifiers},
                        "status": {"type": "string", "enum": ["satisfied", "violated", "unclear"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "status", "reason"],
                    "additionalProperties": False,
                },
            },
        }

        def validate(raw: object) -> dict[str, Any]:
            if not isinstance(raw, dict) or set(raw) != set(properties):
                raise c.ContractError("schema", "judge result")
            if (
                type(raw["verdict"]) is not str
                or raw["verdict"] not in {"accept", "reject", "ambiguous"}
                or type(raw["reason_summary"]) is not str
                or not raw["reason_summary"].strip()
                or not isinstance(raw["criterion_results"], list)
                or len(raw["criterion_results"]) > len(identifiers)
            ):
                raise c.ContractError("schema", "judge result")
            used = set()
            if raw["verdict"] in {"accept", "reject"} and not raw["criterion_results"]:
                raise c.ContractError("semantic", "judge criterion basis missing")
            for item in raw["criterion_results"]:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"id", "status", "reason"}
                    or any(type(item[key]) is not str or not item[key].strip() for key in item)
                    or item["status"] not in {"satisfied", "violated", "unclear"}
                ):
                    raise c.ContractError("schema", "judge criterion")
                if item["id"] not in identifiers or item["id"] in used:
                    raise c.ContractError("semantic", "judge criterion reference")
                used.add(item["id"])
            return raw

        request = c.ModelRequest(
            self.prompt,
            payload,
            "EvaluationJudge",
            "1",
            {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
            self.limits,
        )
        try:
            result = await self.factory()(request, validate)
        except Exception as error:
            return finish(
                Judgment(
                    None,
                    failure={"stage": "judge", "error_code": type(error).__name__},
                    metadata=metadata,
                )
            )
        attempts = []
        for attempt in result.attempts:
            record = asdict(attempt)
            raw = record.get("raw_output")
            record["raw_output_sha256"] = (
                hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None
            )
            if self._secret(record):
                # 비밀값이 섞인 응답은 원문 대신 해시만 보존한다.
                record = {
                    "attempt": attempt.attempt,
                    "raw_output_sha256": record["raw_output_sha256"],
                    "error_code": "judge_trace_contains_configuration_secret",
                    "input_tokens": attempt.input_tokens,
                    "output_tokens": attempt.output_tokens,
                    "latency_ms": attempt.latency_ms,
                }
            attempts.append(record)
        if result.data is not None:
            metadata["judge_output_sha256"] = content_hash(result.data)
        if result.data is not None and self._secret(result.data):
            return finish(
                Judgment(
                    None,
                    tuple(attempts),
                    {"stage": "judge", "error_code": "judge_output_contains_configuration_secret"},
                    metadata=metadata,
                )
            )
        failure = asdict(result.failure) if result.failure else None
        return finish(
            Judgment(
                result.data["verdict"] if result.data else None,
                tuple(attempts),
                failure,
                result.data,
                metadata,
            )
        )
