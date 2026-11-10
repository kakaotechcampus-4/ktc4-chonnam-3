"""동기·비동기 Judge를 같은 감사 형식으로 호출한다. 서비스 런타임은 import하지 않는다."""

import copy
import hashlib
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from judge_context import validate_judge_context

VERDICTS = frozenset({"accept", "reject", "ambiguous"})


@dataclass(frozen=True)
class Judgment:
    verdict: str | None
    attempts: tuple[dict[str, Any], ...] = ()
    failure: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


GraderLike = Callable[[dict[str, Any], str], str | Judgment | Awaitable[str | Judgment]]


def content_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def call_grader(
    grader: GraderLike,
    rubric: dict[str, Any],
    output: str,
    *,
    source_context: dict[str, Any] | None = None,
) -> Judgment:
    # 검수·정답 control 종류·pair·다른 출력은 Judge 입력에 추가하지 않는다.
    visible = {key: copy.deepcopy(rubric[key]) for key in ("allowed", "forbidden")}
    hashes: dict[str, Any] = {
        "rubric_sha256": content_hash(visible),
        "candidate_sha256": content_hash(output),
    }
    started = time.perf_counter()
    try:
        contextual = getattr(grader, "judge_with_context", None)
        if source_context is not None and callable(contextual):
            checked = validate_judge_context(source_context)
            hashes.update(
                source_context_sha256=content_hash(checked),
                source_context_version=checked["schema_version"],
                source_context_status=checked["status"],
                source_context_forwarded=True,
            )
            result = contextual(visible, output, checked)
        else:
            # 기존 두 인자 grader를 재호출하거나 내부 TypeError를 숨기는 fallback은 두지 않는다.
            hashes["source_context_forwarded"] = False
            result = grader(visible, output)
        if inspect.isawaitable(result):
            result = await result
    except Exception as error:
        return Judgment(
            None,
            failure={"stage": "judge", "error_code": type(error).__name__},
            metadata={**hashes, "latency_ms": round((time.perf_counter() - started) * 1000)},
        )
    hashes["latency_ms"] = round((time.perf_counter() - started) * 1000)
    if isinstance(result, Judgment):
        judgment = replace(result, metadata={**hashes, **result.metadata})
    elif type(result) is str:
        judgment = Judgment(result, metadata=hashes)
    else:
        return Judgment(
            None,
            failure={"stage": "judge", "error_code": "invalid_grader_result_type"},
            metadata=hashes,
        )
    # 잘못된 판정도 호출 이력·출력·지문을 보존해 모든 실행 모드에서 같은 실패로 처리한다.
    if judgment.failure is None and (
        type(judgment.verdict) is not str or judgment.verdict not in VERDICTS
    ):
        return replace(
            judgment,
            verdict=None,
            failure={"stage": "judge", "error_code": "invalid_grader_verdict"},
        )
    return judgment
