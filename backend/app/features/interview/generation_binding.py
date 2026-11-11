"""최초 생성의 typed 입력을 보수적으로 묶으며 원문을 상태에 복제하지 않는다."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from uuid import UUID

from devon_ai import contracts as c

STATE_KEY = "director_generation_bindings_v1"
_PROMPT_KEYS = {"task_name", "version", "model", "template_sha256"}


def prompt_identity(prompt: c.PromptSpec) -> dict[str, str]:
    return {
        "task_name": prompt.task_name,
        "version": prompt.version,
        "model": prompt.model,
        "template_sha256": hashlib.sha256(prompt.template.encode()).hexdigest(),
    }


def fingerprint(
    *,
    context: c.Context,
    prompt: c.PromptSpec,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]],
    reference_texts: Mapping[c.BasisRef, str],
    lookup_summary: str,
    tool_results: tuple[c.ToolResult, ...],
) -> str:
    # 투영된 모델 payload의 바이트 지문이 아니다. 투영 전 전체 자료까지 포함하므로
    # 입력에 영향을 줄 수 있는 변경을 넓게 거절하는 typed 입력의 동일성 검사이다.
    value = {
        "context": asdict(context),
        "prompt": prompt_identity(prompt),
        "analysis": None if answer_analysis is None else asdict(answer_analysis.data),
        "past": {key: asdict(item.data) for key, item in prior_analyses.items()},
        "sources": sorted((ref.kind, ref.id, text) for ref, text in reference_texts.items()),
        "lookup_summary": lookup_summary,
        "tool_results": [asdict(item) for item in tool_results],
    }
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def _records(state: Mapping[str, object]) -> dict[str, dict[str, object]]:
    raw = state.get(STATE_KEY, {})
    if type(raw) is not dict or len(raw) > 24:
        raise ValueError("generation_bindings_invalid")
    targets: dict[int, int] = {}
    for key, value in raw.items():
        if type(key) is not str or str(UUID(key)) != key or type(value) is not dict:
            raise ValueError("generation_bindings_invalid")
        target = value.get("target")
        prompt = value.get("prompt")
        digest = value.get("binding")
        if (
            set(value) != {"target", "binding", "prompt"}
            or type(target) is not int
            or not 2 <= target <= 9
            or type(digest) is not str
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or type(prompt) is not dict
            or set(prompt) != _PROMPT_KEYS
            or any(type(item) is not str or not item.strip() for item in prompt.values())
            or prompt["task_name"] != "director"
            or len(prompt["template_sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in prompt["template_sha256"])
        ):
            raise ValueError("generation_bindings_invalid")
        targets[target] = targets.get(target, 0) + 1
        if targets[target] > 3:
            raise ValueError("generation_bindings_invalid")
    return deepcopy(raw)


def capture(
    state: Mapping[str, object],
    *,
    call_id: UUID,
    context: c.Context,
    prompt: c.PromptSpec,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]],
    reference_texts: Mapping[c.BasisRef, str],
    lookup_summary: str,
    tool_results: tuple[c.ToolResult, ...],
) -> dict[str, object]:
    records = _records(state)
    expected = {
        "target": context.turn_no,
        "binding": fingerprint(
            context=context,
            prompt=prompt,
            answer_analysis=answer_analysis,
            prior_analyses=prior_analyses,
            reference_texts=reference_texts,
            lookup_summary=lookup_summary,
            tool_results=tool_results,
        ),
        "prompt": prompt_identity(prompt),
    }
    if str(call_id) in records and records[str(call_id)] != expected:
        raise ValueError("generation_binding_changed")
    records[str(call_id)] = expected
    result = {**deepcopy(state), STATE_KEY: records}
    _records(result)
    return result


def matches(
    state: Mapping[str, object],
    *,
    call_id: UUID,
    context: c.Context,
    prompt: c.PromptSpec,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]],
    reference_texts: Mapping[c.BasisRef, str],
    lookup_summary: str,
    tool_results: tuple[c.ToolResult, ...],
) -> bool:
    try:
        records = _records(state)
        return (
            str(call_id) in records
            and capture(
                state,
                call_id=call_id,
                context=context,
                prompt=prompt,
                answer_analysis=answer_analysis,
                prior_analyses=prior_analyses,
                reference_texts=reference_texts,
                lookup_summary=lookup_summary,
                tool_results=tool_results,
            )
            == state
        )
    except (ValueError, TypeError, AttributeError):
        return False
