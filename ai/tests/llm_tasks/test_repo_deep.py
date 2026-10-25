import asyncio
from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import repo_deep

SHA = "a" * 40
PROMPT = c.PromptSpec("repo_deep", "repo_deep_v1", "fixture-model", "template")
LIMITS = c.CallLimits(10, 1000, 100_000, 100_000)


def _shallow() -> c.ShallowRepoAnalysis:
    return c.ShallowRepoAnalysis(
        repository_id="repo-1",
        head_sha=SHA,
        purpose="캐시 서비스",
        key_features=("캐시 조회",),
        project_types=("backend",),
        tech_stack=("Python",),
        project_role_summary="캐시 기능을 제공하는 프로젝트",
        basis=(c.ShallowBasis("readme", "캐시 서비스를 제공함"),),
        limitations=(),
    )


def _input(**changes: object) -> c.DeepRepoInput:
    values: dict[str, object] = {
        "repository_id": "repo-1",
        "head_sha": SHA,
        "shallow": _shallow(),
        "sources": (
            c.SourceDocument("src/cache.py", "file", "class Cache: pass", "entire file"),
            c.SourceDocument("src/services", "directory", "cache.py\napi.py", "one-level listing"),
        ),
    }
    values.update(changes)
    return c.DeepRepoInput(**values)  # type: ignore[arg-type]


def _area(path: str = "src/cache.py", scope: str = "entire file", **extra: object):
    return {"path": path, "observation": "캐시 클래스", "scope": scope, "limitations": [], **extra}


def _output(*areas: object, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "repository_id": "repo-1",
        "head_sha": SHA,
        "architecture_summary": "단일 서비스 안에 캐시 계층을 둔다",
        "confirmed_technologies": ["Python"],
        "notable_areas": list(areas) if areas else [_area()],
        "limitations": [],
    }
    item.update(overrides)
    return item


class Provider:
    """외부 모델 대역. 응답마다 실제 validator를 실행한다."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[c.ModelRequest] = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        attempt = c.AttemptMetadata(1, "fixture", "fixture-model", "repo_deep_v1", "1", 2, None, 1)
        try:
            data = validator(self.response)
        except c.ContractError as exc:
            return c.ModelResult(None, c.CallFailure(exc.stage, "llm_failed", "x"), (attempt,))
        return c.ModelResult(data, None, (attempt,))


def _analyze(provider: Provider, item: c.DeepRepoInput | None = None, **options: object):
    item = item or _input()
    kwargs: dict[str, object] = {"snapshot_head_sha": SHA, "prompt": PROMPT, "limits": LIMITS}
    kwargs.update(options)
    return asyncio.run(repo_deep.analyze_deep(item, model_call=provider, **kwargs))  # type: ignore[arg-type]


def test_cache_identity_uses_l2_sha_and_prompt_version_not_model() -> None:
    base = repo_deep.cache_identity(_input(), PROMPT)
    assert base == ("repo-1", "l2", SHA, "repo_deep_v1")
    assert repo_deep.cache_identity(_input(), replace(PROMPT, model="other")) == base
    assert repo_deep.cache_identity(_input(), replace(PROMPT, version="repo_deep_v2")) != base


def test_file_and_directory_areas_are_accepted_in_one_call() -> None:
    provider = Provider(
        _output(_area(), _area("src/services", "one-level listing", limitations=["동작 미확인"]))
    )
    result = _analyze(provider)

    assert result.failure is None
    analysis = result.data.data.analysis
    assert [area.path for area in analysis.notable_areas] == ["src/cache.py", "src/services"]
    # limitations가 있는 area는 제한 관찰로 남는다.
    assert analysis.notable_areas[1].limitations == ("동작 미확인",)
    assert result.data.data.rejected_areas == ()
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.payload["repository"]["head_sha"] == SHA
    assert request.output_schema["type"] == "object"
    assert request.max_attempts == 2


def test_invalid_areas_are_split_without_dropping_verified_area() -> None:
    provider = Provider(
        _output(
            _area(),
            _area("missing.py"),
            _area("src/services", "entire file"),
            _area("../secrets.py"),
            _area("src/services", "one-level listing", line=42),
        )
    )
    result = _analyze(provider)

    data = result.data.data
    assert [area.path for area in data.analysis.notable_areas] == ["src/cache.py"]
    rejected = [(item.path, item.stage, item.reason_summary) for item in data.rejected_areas]
    assert rejected == [
        ("missing.py", "semantic", "invalid field: unread source"),
        ("src/services", "semantic", "invalid field: duplicate path"),
        ("../secrets.py", "schema", "invalid field: path"),
        ("src/services", "schema", "invalid field: line"),
    ]


def test_scope_mismatch_and_non_object_area_are_rejected() -> None:
    result = _analyze(Provider(_output(_area(), _area("src/services", "entire file"), "x")))

    data = result.data.data
    assert [area.path for area in data.analysis.notable_areas] == ["src/cache.py"]
    assert [(item.path, item.reason_summary) for item in data.rejected_areas] == [
        ("src/services", "invalid field: read scope mismatch"),
        (None, "invalid field: NotableArea"),
    ]


def test_directory_area_without_limitations_is_rejected() -> None:
    result = _analyze(Provider(_output(_area(), _area("src/services", "one-level listing"))))

    data = result.data.data
    assert [area.path for area in data.analysis.notable_areas] == ["src/cache.py"]
    assert [(item.path, item.stage, item.reason_summary) for item in data.rejected_areas] == [
        ("src/services", "semantic", "invalid field: directory limitations missing")
    ]


def test_too_many_areas_is_retryable_schema_failure() -> None:
    """개수 초과는 schema라 공통 호출 계층의 재시도 대상이다. 앞 5개만 잘라 쓰지 않는다."""
    areas = [_area(observation=str(i)) for i in range(6)]
    with pytest.raises(c.ContractError) as error:
        c.parse_deep_analysis(_output(notable_areas=areas), source=_input())
    assert (error.value.stage, error.value.field) == ("schema", "notable area count")


def test_all_schema_invalid_areas_request_gateway_retry() -> None:
    with pytest.raises(c.ContractError) as error:
        c.parse_deep_analysis(_output(_area(observation="")), source=_input())

    assert (error.value.stage, error.value.field) == ("schema", "notable areas")


@pytest.mark.parametrize(
    "overrides",
    [
        {"head_sha": "b" * 40, "architecture_summary": ""},
        {"repository_id": "repo-2", "architecture_summary": ""},
        {"head_sha": "b" * 40, "notable_areas": "invalid"},
        {"repository_id": "repo-2", "unexpected": True},
    ],
)
def test_other_output_errors_cannot_hide_repository_ref_mismatch(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(c.ContractError) as error:
        c.parse_deep_analysis(_output(**overrides), source=_input())

    assert (error.value.stage, error.value.field) == ("semantic", "repository ref")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_id", None),
        ("repository_id", ""),
        ("head_sha", None),
        ("head_sha", "not-a-sha"),
        ("head_sha", "z" * 40),
    ],
)
def test_malformed_reference_is_schema_before_comparing_identity(field: str, value: object) -> None:
    with pytest.raises(c.ContractError) as error:
        c.parse_deep_analysis(_output(**{field: value}), source=_input())

    assert (error.value.stage, error.value.field) == ("schema", field)


@pytest.mark.parametrize(
    "areas",
    [
        [],
        [_area("missing.py")],
        [_area("src/cache.py"), _area("src/cache.py", observation="다른 주장")],
    ],
)
def test_no_verified_area_returns_no_analysis(areas: list[object]) -> None:
    result = _analyze(Provider(_output(notable_areas=areas)))

    assert result.failure is None
    assert result.data.data.analysis is None
    assert len(result.data.data.rejected_areas) == len(areas)


@pytest.mark.parametrize(
    ("response", "stage"),
    [
        (_output(head_sha="b" * 40), "semantic"),
        (_output(repository_id="repo-2"), "semantic"),
        (_output(notable_areas=[_area(observation=str(i)) for i in range(6)]), "schema"),
        (_output(user_contribution="80%"), "schema"),
        ({k: v for k, v in _output().items() if k != "architecture_summary"}, "schema"),
        (_output(notable_areas="src/cache.py"), "schema"),
        (["not", "an", "object"], "schema"),
    ],
)
def test_whole_result_failures_are_not_partial_success(response: object, stage: str) -> None:
    result = _analyze(Provider(response))

    assert result.data is None
    assert result.failure.stage == stage


@pytest.mark.parametrize(
    ("item", "options", "stage"),
    [
        (None, {"snapshot_head_sha": "b" * 40}, "semantic"),
        (_input(sources=()), {}, "semantic"),
        (None, {"prompt": replace(PROMPT, task_name="repo_shallow")}, "schema"),
        (None, {"limits": None}, "schema"),
    ],
)
def test_invalid_input_is_rejected_before_model_call(
    item: c.DeepRepoInput | None, options: dict[str, object], stage: str
) -> None:
    provider = Provider(_output())
    result = _analyze(provider, item, **options)

    assert provider.requests == []
    assert result.attempts == ()
    assert result.failure.stage == stage
    assert result.failure.error_code == "repo_deep_input_invalid"
