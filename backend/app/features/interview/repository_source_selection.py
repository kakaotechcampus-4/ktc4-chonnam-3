"""확인한 전체 경로와 모델에 전달할 유한 후보를 구분한다."""

from collections import deque
from collections.abc import Iterator

from devon_ai import contracts as c

from app.integrations.llm.client import request_size


def summarized_limitations(notes: tuple[str, ...]) -> tuple[str, ...]:
    """모델에는 유한 요약만 주고 원래 목록은 별도 inventory에 보존한다."""
    if len(notes) <= 8 and all(len(note) <= 160 for note in notes):
        return notes
    return (
        f"구조 확인 한계 {len(notes)}건 중 최대 8건의 앞부분만 표시합니다. "
        "전체는 고정 SHA inventory에 보존합니다.",
        *(note if len(note) <= 160 else note[:157] + "..." for note in notes[:8]),
    )


def _module_order(paths: tuple[str, ...]) -> Iterator[str]:
    modules: dict[str, dict[str, deque[str]]] = {}
    for path in paths:
        parent = path.rpartition("/")[0]
        module = path.split("/", 1)[0] if parent else ""
        modules.setdefault(module, {}).setdefault(parent, deque()).append(path)
    pending = deque(deque(parents.values()) for parents in modules.values())
    while pending:
        parents = pending.popleft()
        files = parents.popleft()
        yield files.popleft()
        if files:
            parents.append(files)
        if parents:
            pending.append(parents)


def selection_window(
    *,
    shallow: c.ShallowRepoAnalysis,
    prompt: c.PromptSpec,
    candidates: tuple[str, ...],
    limitations: tuple[str, ...],
    max_selected_files: int,
    limits: c.CallLimits,
    max_enum_values: int = 900,
    max_enum_characters: int = 14000,
) -> tuple[c.ModelRequest, tuple[str, ...], tuple[str, ...]]:
    """프롬프트·payload·중복 enum까지 포함한 실제 요청 바이트 안에서만 후보를 나눈다."""
    from dataclasses import asdict

    def build(paths: tuple[str, ...], notes: tuple[str, ...]) -> c.ModelRequest:
        return c.ModelRequest(
            prompt=prompt,
            payload={
                "operation": "select",
                "repository_id": shallow.repository_id,
                "head_sha": shallow.head_sha,
                "shallow": asdict(shallow),
                "candidates": [{"path": path, "kind": "file"} for path in paths],
                "limitations": list(notes),
                "max_selected_files": max_selected_files,
            },
            schema_name="RepoDeepSourceSelection",
            schema_version="1",
            output_schema={
                "type": "object",
                "properties": {
                    "selected_paths": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": max_selected_files,
                        "items": {"type": "string", "enum": list(paths)},
                    }
                },
                "required": ["selected_paths"],
                "additionalProperties": False,
            },
            limits=limits,
            max_attempts=1,
        )

    if any(
        type(value) is not int or value <= 0 for value in (max_enum_values, max_enum_characters)
    ):
        raise c.ContractError("schema", "source selection enum limits")
    bounded_notes = summarized_limitations(limitations)
    complete = build(candidates, bounded_notes)
    if (
        len(candidates) <= max_enum_values
        and sum(map(len, candidates)) <= max_enum_characters
        and request_size(complete) <= limits.max_input_bytes
    ):
        return complete, candidates, ()
    note = (
        "모델 입력 상한 또는 공급자 스키마 상한으로 "
        f"전체 구조 후보 {len(candidates)}개 중 일부만 모듈별로 나누어 "
        "선정 입력에 전달했습니다. 전달하지 않은 경로는 이번 모델 선정에서 미확인입니다."
    )
    notes = (*bounded_notes, note)
    empty = build((), notes)
    overhead = request_size(empty)
    used = overhead
    selected: list[str] = []
    enum_characters = 0
    if overhead < limits.max_input_bytes:
        for path in _module_order(candidates):
            if len(selected) == max_enum_values:
                break
            if enum_characters + len(path) > max_enum_characters:
                continue
            # 경로 한 개의 실제 직렬화 차이를 재사용해 전체 목록을 매번 직렬화하지 않는다.
            # 두 목록(payload·enum)의 다음 항목에는 각각 JSON 구분자 ', '가 추가된다.
            added = request_size(build((path,), notes)) - overhead + (4 if selected else 0)
            if used + added <= limits.max_input_bytes:
                selected.append(path)
                used += added
                enum_characters += len(path)
    result = build(tuple(selected), notes)
    if request_size(result) != used:
        raise c.ContractError("schema", "source selection serialization size")
    return result, tuple(selected), (note,)
