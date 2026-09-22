"""Exercise the real AI validator through the BE HTTP boundary, without a provider."""

import json
from dataclasses import replace
from functools import partial

import httpx
from devon_ai import contracts as c
from pydantic import SecretStr

from app.integrations.llm.client import CallBudget, call_model

SHA = "a" * 40


def source(repository_id):
    return c.ShallowRepoInput(
        repository_id,
        SHA,
        "cache API",
        "Cache API",
        False,
        (c.LanguageBytes("Python", 100),),
        10,
        2,
        (),
    )


def candidate(repository_id):
    return {
        "repository_id": repository_id,
        "head_sha": SHA,
        "purpose": "Cache API",
        "key_features": ["cache lookup"],
        "project_types": ["backend"],
        "tech_stack": ["Python"],
        "project_role_summary": "Provides a cache API",
        "basis": [{"kind": "readme", "claim": "Cache API"}],
        "limitations": ["Execution not checked"],
    }


def model_response(items):
    return {
        "id": "resp_fixture",
        "model": "fixture-model",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps({"items": items})}],
            }
        ],
    }


def request(inputs):
    # The feature owns its schema. No schema generator or evaluation metadata is injected.
    properties = {
        name: {"type": "string"}
        for name in (
            "repository_id",
            "head_sha",
            "purpose",
            "project_role_summary",
        )
    }
    properties.update(
        {
            name: {"type": "array", "items": {"type": "string"}}
            for name in (
                "key_features",
                "project_types",
                "tech_stack",
                "limitations",
            )
        }
    )
    properties["basis"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "claim": {"type": "string"},
            },
            "required": ["kind", "claim"],
            "additionalProperties": False,
        },
    }
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    return c.ModelRequest(
        c.PromptSpec("repo_shallow", "repo_shallow_v1", "fixture-model", "Summarize the input."),
        {
            "repositories": [
                {
                    "repository_id": item.repository_id,
                    "head_sha": item.head_sha,
                    "readme_text": item.readme_text,
                }
                for item in inputs
            ]
        },
        "shallow_fixture",
        "1",
        schema,
        c.CallLimits(1, 500, 8192, 8192),
    )


def validator(inputs):
    def validate(raw):
        if not isinstance(raw, dict) or "items" not in raw:
            raise c.ContractError("schema", "items")
        return c.parse_shallow_batch(raw["items"], inputs=inputs)

    return validate


async def test_partial_schema_failure_preserves_valid_repos_and_shares_total_budget():
    inputs = (source("good"), source("retry"), source("stale"))
    invalid = {**candidate("retry"), "purpose": 123}
    stale = {**candidate("stale"), "head_sha": "b" * 40}
    sent = []

    def transport(req):
        sent.append(json.loads(req.content))
        items = [candidate("good"), invalid, stale] if len(sent) == 1 else [candidate("retry")]
        return httpx.Response(200, json=model_response(items))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        call = partial(
            call_model, api_key=SecretStr("fixture-key"), http_client=http, budget=CallBudget()
        )
        first = await call(request(inputs), validator(inputs))
        assert first.succeeded
        batch = first.data.data
        assert [item.repository_id for item in batch.succeeded] == ["good"]
        assert {(item.repository_id, item.stage) for item in batch.failed} == {
            ("retry", "schema"),
            ("stale", "semantic"),
        }
        retry_ids = {item.repository_id for item in batch.failed if item.stage == "schema"}
        subset = tuple(item for item in inputs if item.repository_id in retry_ids)
        second = await call(request(subset), validator(subset))
        assert second.succeeded and second.data.data.failed == ()
        assert [item.repository_id for item in second.data.data.succeeded] == ["retry"]
        assert [item.attempt for item in second.attempts] == [1, 2]
        third = await call(request(subset), validator(subset))
        assert third.failure.stage == "budget"

    assert len(sent) == 2
    second_input = json.loads(sent[1]["input"][0]["content"][0]["text"])
    assert [item["repository_id"] for item in second_input["repositories"]] == ["retry"]
    assert first.data.data.succeeded == batch.succeeded  # original valid data is retained


async def test_retryable_transport_failure_leaves_no_extra_batch_retry_budget():
    inputs = (source("one"),)
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=model_response([candidate("one")]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        call = partial(
            call_model, api_key=SecretStr("fixture-key"), http_client=http, budget=CallBudget()
        )
        result = await call(request(inputs), validator(inputs))
        assert result.succeeded and len(result.attempts) == 2
        exhausted = await call(
            replace(request(inputs), payload={"repositories": []}), validator(inputs)
        )
        assert exhausted.failure.stage == "budget"
    assert calls == 2
