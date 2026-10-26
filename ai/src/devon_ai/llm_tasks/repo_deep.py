"""L2 저장소 정밀 분석. primary 선정·고정 ref 원문 조회·prompt·저장은 BE 책임이다(task-05)."""

from dataclasses import asdict

from devon_ai import contracts as c

type CacheIdentity = tuple[str, str, str, str]
type DeepChecked = c.ContractChecked[c.DeepAnalysisResult]


def cache_identity(item: c.DeepRepoInput, prompt: c.PromptSpec) -> CacheIdentity:
    """repo_analyses UNIQUE 키. analysis_level은 DB 값 l2, model은 재사용 판정에 넣지 않는다."""
    return (item.repository_id, "l2", item.head_sha, prompt.version)


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _output_schema() -> dict[str, object]:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    area = _object({"path": text, "observation": text, "scope": text, "limitations": texts})
    return _object(
        {
            "repository_id": text,
            "head_sha": text,
            "architecture_summary": text,
            "confirmed_technologies": texts,
            "notable_areas": {"type": "array", "items": area},
            "limitations": texts,
        }
    )


async def analyze_deep(
    item: c.DeepRepoInput,
    *,
    snapshot_head_sha: str,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[DeepChecked],
) -> c.ModelResult[DeepChecked]:
    """primary 저장소 하나의 L2 후보를 만들고 notable area별로 검증한다.

    snapshot_head_sha는 면접 session_repositories의 고정 ref다. 분석 입력의 SHA와 다르면 모델을
    부르지 않는다. 성공 결과는 검증 완료이며 준비 성공은 analysis가 있을 때만이다.
    """
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "repo_deep":
            raise c.ContractError("schema", "repo_deep prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "repo_deep limits")
        if type(item) is not c.DeepRepoInput:
            raise c.ContractError("schema", "deep input")
        # 원격 최신 SHA나 다른 면접의 ref로 분석하면 근거가 면접 snapshot과 어긋난다.
        if item.head_sha != snapshot_head_sha:
            raise c.ContractError("semantic", "snapshot head_sha")
        # 읽은 원문이 없으면 검증 가능한 notable area가 나올 수 없어 호출 비용만 쓴다.
        if not item.sources:
            raise c.ContractError("semantic", "deep sources")
    except c.ContractError as exc:
        failure = c.CallFailure(exc.stage, "repo_deep_input_invalid", "L2 input rejected.")
        return c.ModelResult(None, failure, ())
    request = c.ModelRequest(
        prompt=prompt,
        payload={"repository": asdict(item)},
        schema_name="RepoDeep",
        schema_version="1",
        output_schema=_output_schema(),
        limits=limits,
    )
    return await model_call(request, lambda payload: c.parse_deep_analysis(payload, source=item))
