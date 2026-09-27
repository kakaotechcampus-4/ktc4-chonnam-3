import asyncio
from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import repo_shallow

SHA = "a" * 40
PROMPT = c.PromptSpec("repo_shallow", "repo_shallow_v1", "fixture-model", "template")


def _input(repository_id: str = "repo-1") -> c.ShallowRepoInput:
    return c.ShallowRepoInput(
        repository_id=repository_id,
        head_sha=SHA,
        description="cache service",
        readme_text="A cache service",
        readme_truncated=False,
        languages=(c.LanguageBytes("Python", 120),),
        commit_count=10,
        user_commit_count=3,
        collection_errors=(),
    )


def test_cache_identity_is_the_repo_analyses_unique_key() -> None:
    assert repo_shallow.cache_identity(_input(), PROMPT) == (
        "repo-1",
        "l1",
        SHA,
        "repo_shallow_v1",
    )


def test_model_change_keeps_cache_identity() -> None:
    other_model = replace(PROMPT, model="other-model")
    assert repo_shallow.cache_identity(_input(), other_model) == repo_shallow.cache_identity(
        _input(), PROMPT
    )


def test_head_sha_or_prompt_version_change_misses_cache() -> None:
    base = repo_shallow.cache_identity(_input(), PROMPT)
    assert repo_shallow.cache_identity(replace(_input(), head_sha="b" * 40), PROMPT) != base
    assert repo_shallow.cache_identity(_input(), replace(PROMPT, version="repo_shallow_v2")) != base


LIMITS = c.CallLimits(10, 1000, 100_000, 100_000)


def _output(repository_id: str = "repo-1", **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "repository_id": repository_id,
        "head_sha": SHA,
        "purpose": "캐시 서비스",
        "key_features": ["캐시 조회"],
        "project_types": ["backend"],
        "tech_stack": ["Python"],
        "project_role_summary": "캐시 기능을 제공하는 프로젝트",
        "basis": [{"kind": "readme", "claim": "캐시 서비스를 제공함"}],
        "limitations": ["실행 동작 미확인"],
    }
    item.update(overrides)
    return item


def _metadata(attempt: int = 1) -> c.AttemptMetadata:
    return c.AttemptMetadata(
        attempt, "fixture", "fixture-model", "repo_shallow_v1", "1", 2, None, 1
    )


class Provider:
    """외부 모델 대역. 응답마다 실제 validator를 실행한다. CallFailure는 그대로 반환한다."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[c.ModelRequest] = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        attempt = _metadata(len(self.requests))
        response = self.responses.pop(0)
        if type(response) is c.CallFailure:
            return c.ModelResult(None, response, (attempt,))
        try:
            data = validator(response)
        except c.ContractError as exc:
            failure = c.CallFailure(exc.stage, "llm_failed", "invalid")
            return c.ModelResult(None, failure, (attempt,))
        return c.ModelResult(data, None, (attempt,))


def _analyze(provider: Provider, *inputs: c.ShallowRepoInput):
    return asyncio.run(
        repo_shallow.analyze_shallow_batch(
            inputs or (_input(),), prompt=PROMPT, limits=LIMITS, model_call=provider
        )
    )


def _ids(items) -> list[str | None]:
    return [item.repository_id for item in items]


def test_valid_batch_returns_every_repository_in_one_call() -> None:
    provider = Provider({"repositories": [_output("repo-2"), _output("repo-1")]})
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert result.failure is None
    assert sorted(_ids(result.data.data.succeeded)) == ["repo-1", "repo-2"]
    assert result.data.data.failed == ()
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert [item["repository_id"] for item in request.payload["repositories"]] == [
        "repo-1",
        "repo-2",
    ]
    assert request.output_schema["type"] == "object"


def test_provider_failure_is_returned_without_retry() -> None:
    timeout = c.CallFailure("timeout", "llm_timeout", "timed out")
    provider = Provider(timeout)
    result = _analyze(provider)

    assert result.failure == timeout
    assert len(provider.requests) == 1


def test_output_without_repositories_object_is_schema_failure() -> None:
    provider = Provider([_output()])
    result = _analyze(provider)

    assert result.failure is not None and result.failure.stage == "schema"


def test_schema_failed_item_is_retried_alone_and_merged() -> None:
    provider = Provider(
        {"repositories": [_output("repo-1"), _output("repo-2", purpose=3)]},
        {"repositories": [_output("repo-2")]},
    )
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert [item["repository_id"] for item in provider.requests[1].payload["repositories"]] == [
        "repo-2"
    ]
    # 첫 호출이 1회를 썼으므로 재요청은 남은 1회로 제한된다.
    assert provider.requests[1].max_attempts == 1
    assert sorted(_ids(result.data.data.succeeded)) == ["repo-1", "repo-2"]
    assert result.data.data.failed == ()
    assert [attempt.attempt for attempt in result.attempts] == [1, 2]


def test_semantic_failed_item_is_not_retried() -> None:
    provider = Provider({"repositories": [_output("repo-1"), _output("repo-2", head_sha="b" * 40)]})
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert len(provider.requests) == 1
    assert _ids(result.data.data.succeeded) == ["repo-1"]
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [("repo-2", "semantic")]


def test_failed_retry_keeps_first_results_and_original_failure() -> None:
    provider = Provider(
        {"repositories": [_output("repo-1"), _output("repo-2", purpose=3)]},
        c.CallFailure("budget", "llm_budget_exhausted", "no budget"),
    )
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert result.failure is None
    assert _ids(result.data.data.succeeded) == ["repo-1"]
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [("repo-2", "schema")]
    assert len(result.attempts) == 2


def test_schema_failure_without_repository_id_is_not_retried() -> None:
    provider = Provider({"repositories": [_output("repo-1"), _output(None)]})
    result = _analyze(provider)

    assert len(provider.requests) == 1
    assert _ids(result.data.data.succeeded) == ["repo-1"]
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [(None, "schema")]


def test_retry_mentioning_an_earlier_success_does_not_fail_it() -> None:
    provider = Provider(
        {"repositories": [_output("repo-1"), _output("repo-2", purpose=3)]},
        {"repositories": [_output("repo-2"), _output("repo-1")]},
    )
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert sorted(_ids(result.data.data.succeeded)) == ["repo-1", "repo-2"]
    assert result.data.data.failed == ()


@pytest.mark.parametrize("key", ["architecture_summary", "notable_areas", "contribution_ratio"])
def test_l2_or_contribution_field_fails_the_item_instead_of_being_dropped(key: str) -> None:
    forbidden = _output("repo-2", **{key: "x"})
    provider = Provider(
        {"repositories": [_output("repo-1"), forbidden]},
        {"repositories": [forbidden]},
    )
    result = _analyze(provider, _input("repo-1"), _input("repo-2"))

    assert _ids(result.data.data.succeeded) == ["repo-1"]
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [("repo-2", "schema")]


@pytest.mark.parametrize(
    "failure",
    [
        c.CallFailure("parse", "llm_parse_failed", "broken json"),
        c.CallFailure("semantic", "llm_failed", "refused"),
    ],
)
def test_parse_and_refusal_failures_reach_the_caller_unchanged(failure: c.CallFailure) -> None:
    provider = Provider(failure)
    result = _analyze(provider)

    assert result.failure == failure
    assert result.data is None
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("inputs", "prompt"),
    [
        ((_input(),), replace(PROMPT, task_name="repo_deep")),
        ((), PROMPT),
        ((_input("repo-1"), _input("repo-1")), PROMPT),
        ([_input()], PROMPT),
        (("repo-1",), PROMPT),
        ((_input(),), {"task_name": "repo_shallow"}),
    ],
    ids=["wrong-prompt", "empty", "duplicate-id", "list-inputs", "not-input", "not-prompt"],
)
def test_invalid_input_fails_before_any_model_call(inputs, prompt) -> None:
    provider = Provider()
    result = asyncio.run(
        repo_shallow.analyze_shallow_batch(
            inputs, prompt=prompt, limits=LIMITS, model_call=provider
        )
    )

    assert result.failure is not None and result.failure.stage in ("schema", "semantic")
    assert result.attempts == ()
    assert provider.requests == []


def test_stale_head_sha_with_extra_key_is_semantic_and_not_retried() -> None:
    provider = Provider(
        {"repositories": [_output("repo-1", head_sha="b" * 40, contribution_ratio=0.9)]}
    )
    result = _analyze(provider)

    assert len(provider.requests) == 1
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [("repo-1", "semantic")]


def test_no_retry_when_first_call_already_used_both_attempts() -> None:
    # BE가 CallBudget을 공유하지 않은 model_call을 넘겨도 총 2회를 넘지 않아야 한다.
    requests: list[c.ModelRequest] = []

    async def two_attempts_then_partial(request, validator):
        requests.append(request)
        data = validator({"repositories": [_output("repo-1"), _output("repo-2", purpose=3)]})
        return c.ModelResult(data, None, (_metadata(1), _metadata(2)))

    result = asyncio.run(
        repo_shallow.analyze_shallow_batch(
            (_input("repo-1"), _input("repo-2")),
            prompt=PROMPT,
            limits=LIMITS,
            model_call=two_attempts_then_partial,
        )
    )

    assert len(requests) == 1
    assert [(f.repository_id, f.stage) for f in result.data.data.failed] == [("repo-2", "schema")]


def test_invalid_limits_fail_before_any_model_call() -> None:
    provider = Provider()
    result = asyncio.run(
        repo_shallow.analyze_shallow_batch(
            (_input(),), prompt=PROMPT, limits={"timeout_seconds": 10}, model_call=provider
        )
    )

    assert result.failure is not None and result.failure.stage == "schema"
    assert provider.requests == []
