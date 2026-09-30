"""L1 저장소 기본 분석. prompt 로드·provider I/O·저장은 BE 책임이다(task-04 문서)."""

from collections.abc import Callable
from dataclasses import asdict

from devon_ai import contracts as c

type CacheIdentity = tuple[str, str, str, str]
type ShallowChecked = c.ContractChecked[c.ShallowBatchResult]


def cache_identity(item: c.ShallowRepoInput, prompt: c.PromptSpec) -> CacheIdentity:
    """repo_analyses UNIQUE 키. analysis_level은 DB 값 l1, model은 재사용 판정에 넣지 않는다."""
    return (item.repository_id, "l1", item.head_sha, prompt.version)


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _output_schema() -> dict[str, object]:
    # strict JSON Schema는 최상위가 object여야 하므로 배치를 repositories로 감싼다.
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    basis = _object(
        {
            "kind": {
                "type": "string",
                "enum": ["readme", "description", "languages", "commit_metadata"],
            },
            "claim": text,
        }
    )
    item = _object(
        {
            "repository_id": text,
            "head_sha": text,
            "purpose": text,
            "key_features": texts,
            "project_types": texts,
            "tech_stack": texts,
            "project_role_summary": text,
            "basis": {"type": "array", "items": basis},
            "limitations": texts,
        }
    )
    return _object({"repositories": {"type": "array", "items": item}})


def _request(
    inputs: tuple[c.ShallowRepoInput, ...],
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    max_attempts: int = 2,
) -> c.ModelRequest:
    return c.ModelRequest(
        prompt=prompt,
        payload={"repositories": [asdict(item) for item in inputs]},
        schema_name="RepoShallowBatch",
        schema_version="1",
        output_schema=_output_schema(),
        limits=limits,
        max_attempts=max_attempts,
    )


def _validator(inputs: tuple[c.ShallowRepoInput, ...]) -> Callable[[object], ShallowChecked]:
    def validate(payload: object) -> ShallowChecked:
        if type(payload) is not dict or set(payload) != {"repositories"}:
            raise c.ContractError("schema", "shallow batch")
        return c.parse_shallow_batch(payload["repositories"], inputs=inputs)

    return validate


async def analyze_shallow_batch(
    inputs: tuple[c.ShallowRepoInput, ...],
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[ShallowChecked],
) -> c.ModelResult[ShallowChecked]:
    """L1 후보를 만들고 식별된 schema 실패 저장소만 한 번 재요청한다.

    두 호출의 시도 합은 2회를 넘지 않는다. model_call이 CallBudget을 공유하면 호출 계층도 같은
    상한을 지킨다. semantic 실패는 재호출하지 않는다. 결과의 성공은 배치 검증 완료이며 모든
    저장소 성공을 뜻하지 않는다.
    """
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "repo_shallow":
            raise c.ContractError("schema", "repo_shallow prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "repo_shallow limits")
        # list 등은 검증기 안에서 schema 오류가 되어 유료 재시도를 부르므로 호출 전에 막는다.
        if (
            type(inputs) is not tuple
            or not inputs
            or any(type(item) is not c.ShallowRepoInput for item in inputs)
        ):
            raise c.ContractError("schema", "shallow inputs")
        if len({item.repository_id for item in inputs}) != len(inputs):
            raise c.ContractError("semantic", "input repository ids")
    except c.ContractError as exc:
        # 모델을 부르기 전에 거절해 잘못된 입력으로 호출 비용을 쓰지 않는다.
        failure = c.CallFailure(exc.stage, "repo_shallow_input_invalid", "L1 input rejected.")
        return c.ModelResult(None, failure, ())
    first = await model_call(_request(inputs, prompt, limits), _validator(inputs))
    if first.data is None:
        return first
    retry_ids = {
        item.repository_id
        for item in first.data.data.failed
        if item.stage == "schema" and item.repository_id is not None
    }
    # 첫 호출이 쓴 시도 수로 총 2회 상한을 직접 지킨다. CallBudget을 공유하지 않아도 넘지 않는다.
    used = len(first.attempts)
    if not retry_ids or used >= 2:
        return first
    retry_inputs = tuple(item for item in inputs if item.repository_id in retry_ids)
    retry = await model_call(
        _request(retry_inputs, prompt, limits, max_attempts=2 - used), _validator(retry_inputs)
    )
    # 재요청이 실패하면 첫 배치의 성공과 원래 실패 기록을 그대로 돌려준다.
    data = first.data if retry.data is None else c.merge_shallow_retry(first.data, retry.data)
    return c.ModelResult(data, None, first.attempts + retry.attempts)
