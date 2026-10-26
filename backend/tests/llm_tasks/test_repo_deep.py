"""L2 BE 연결: 가짜 HTTP 공급자로 호출 상한과 repo_analyses 행 매핑을 검사한다. DB는 쓰지 않는다."""

import json
import uuid

import httpx
import pytest
from devon_ai import contracts as c
from pydantic import SecretStr

from app.core.config import LLMSettings, Settings
from app.llm_tasks import repo_deep

SHA = "a" * 40
REPO = str(uuid.UUID(int=1))
PROMPT = c.PromptSpec("repo_deep", "repo_deep_v1", "configured-model", "fixture prompt")
SETTINGS = LLMSettings(
    openai_api_key=SecretStr("fixture-key"),
    llm_default_model="configured-model",
    llm_timeout_seconds=1,
    llm_max_output_tokens=512,
    llm_max_input_bytes=65536,
    llm_max_response_bytes=65536,
)


def _input() -> c.DeepRepoInput:
    shallow = c.ShallowRepoAnalysis(
        repository_id=REPO,
        head_sha=SHA,
        purpose="캐시 서비스",
        key_features=("캐시 조회",),
        project_types=("backend",),
        tech_stack=("Python",),
        project_role_summary="캐시 기능을 제공하는 프로젝트",
        basis=(c.ShallowBasis("readme", "캐시 서비스를 제공함"),),
        limitations=(),
    )
    return c.DeepRepoInput(
        repository_id=REPO,
        head_sha=SHA,
        shallow=shallow,
        sources=(c.SourceDocument("src/cache.py", "file", "class Cache: pass", "entire file"),),
    )


def _area(path: str = "src/cache.py") -> dict[str, object]:
    return {"path": path, "observation": "캐시 클래스", "scope": "entire file", "limitations": []}


def _output(*areas: dict[str, object], **overrides: object) -> str:
    item: dict[str, object] = {
        "repository_id": REPO,
        "head_sha": SHA,
        "architecture_summary": "단일 서비스 안에 캐시 계층을 둔다",
        "confirmed_technologies": ["Python"],
        "notable_areas": list(areas) if areas else [_area()],
        "limitations": [],
    }
    item.update(overrides)
    return json.dumps(item, ensure_ascii=False)


def _response(text: str) -> dict[str, object]:
    return {
        "id": "resp_repo_deep_fixture",
        "model": "actual-model-snapshot",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 60},
    }


async def _run_result(
    replies: list[object], *, settings: LLMSettings = SETTINGS, snapshot: str = SHA
):
    sent: list[httpx.Request] = []
    pending = iter(replies)

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        reply = next(pending)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=_response(str(reply)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await repo_deep.analyze_repository(
            _input(), snapshot_head_sha=snapshot, prompt=PROMPT, settings=settings, http_client=http
        )
    return result, sent


async def _run(replies: list[object], *, settings: LLMSettings = SETTINGS, snapshot: str = SHA):
    result, sent = await _run_result(replies, settings=settings, snapshot=snapshot)
    return repo_deep.to_repo_analysis_row(result, _input(), PROMPT), sent


async def test_verified_area_is_stored_as_l2_success() -> None:
    raw = _output(_area(), _area("missing.py"))
    row, sent = await _run([raw])

    assert len(sent) == 1
    body = json.loads(sent[0].content)
    assert body["model"] == "configured-model" and body["max_output_tokens"] == 512
    assert row == {
        "repository_id": uuid.UUID(REPO),
        "analysis_level": "l2",
        "head_sha": SHA,
        "prompt_version": "repo_deep_v1",
        "model": "actual-model-snapshot",
        "status": "succeeded",
        "error_code": None,
        "batch_position": None,
        "summary": None,
        "tech_stack": ["Python"],
        "notable_areas": [_area()],
        "result": row["result"],
        "raw_output": raw,
        "input_tokens": 100,
        "output_tokens": 60,
        "latency_ms": row["latency_ms"],
        "attempt": 1,
    }
    # 거절한 area는 행의 notable_areas에 섞지 않고 result에만 남긴다.
    (rejected,) = row["result"]["rejected_areas"]
    assert rejected == {
        "path": "missing.py",
        "stage": "semantic",
        "reason_summary": "invalid field: unread source",
    }


async def test_no_verified_area_fails_without_retry_and_keeps_rejections() -> None:
    row, sent = await _run([_output(_area("missing.py"))])

    assert len(sent) == 1
    assert (row["status"], row["error_code"]) == ("failed", "llm_failed")
    assert row["notable_areas"] is None and row["tech_stack"] == []
    assert row["result"]["analysis"] is None
    assert len(row["result"]["rejected_areas"]) == 1


async def test_too_many_areas_is_retried_once_within_two_requests() -> None:
    too_many = _output(*[_area() | {"observation": str(i)} for i in range(6)])
    row, sent = await _run([too_many, _output()])

    assert len(sent) == 2
    assert (row["status"], row["attempt"]) == ("succeeded", 2)


async def test_all_schema_invalid_areas_retry_and_preserve_attempt_errors() -> None:
    invalid = _output(_area() | {"observation": ""})
    valid = _output()
    result, sent = await _run_result([invalid, valid])

    assert len(sent) == 2
    assert result.failure is None and result.data.data.analysis is not None
    assert [attempt.error_stage for attempt in result.attempts] == ["schema", None]
    assert [attempt.raw_output for attempt in result.attempts] == [invalid, valid]
    assert result.attempts[0].error_code == "llm_failed"


async def test_valid_area_is_preserved_when_another_area_has_schema_error() -> None:
    result, sent = await _run_result([_output(_area(), _area("missing.py") | {"observation": ""})])

    assert len(sent) == 1 and result.failure is None
    assert [area.path for area in result.data.data.analysis.notable_areas] == ["src/cache.py"]
    assert [(area.path, area.stage) for area in result.data.data.rejected_areas] == [
        ("missing.py", "schema")
    ]


async def test_mixed_schema_and_semantic_rejections_do_not_retry_semantic_areas() -> None:
    invalid = _output(_area() | {"observation": ""}, _area("missing.py"))
    result, sent = await _run_result([invalid, _output()])

    assert len(sent) == len(result.attempts) == 1 and result.failure is None
    assert result.data.data.analysis is None
    assert [area.stage for area in result.data.data.rejected_areas] == ["schema", "semantic"]
    assert repo_deep.to_repo_analysis_row(result, _input(), PROMPT)["status"] == "failed"


@pytest.mark.parametrize(
    "first",
    [
        httpx.ReadTimeout("timed out"),
        httpx.Response(503),
        "not JSON",
        _output(_area() | {"observation": ""}),
    ],
    ids=["timeout", "provider", "parse", "schema"],
)
async def test_schema_area_retry_never_resets_the_total_two_request_budget(first: object) -> None:
    invalid = _output(_area() | {"observation": ""})
    result, sent = await _run_result([first, invalid, _output()])

    assert len(sent) == len(result.attempts) == 2
    assert result.data is None and result.failure.stage == "schema"
    assert result.attempts[-1].error_stage == "schema"


@pytest.mark.parametrize("field", ["head_sha", "repository_id"])
async def test_mismatched_ref_with_bad_summary_is_semantic_and_never_retried(field: str) -> None:
    invalid = _output(
        **{field: "b" * 40 if field == "head_sha" else str(uuid.UUID(int=2))},
        architecture_summary="",
    )
    result, sent = await _run_result([invalid, _output()])

    assert len(sent) == len(result.attempts) == 1
    assert result.data is None and result.failure.stage == "semantic"
    assert result.attempts[0].error_stage == "semantic"
    assert result.attempts[0].raw_output == invalid


async def test_malformed_ref_is_schema_and_uses_only_the_remaining_retry() -> None:
    result, sent = await _run_result([_output(head_sha="not-a-sha"), _output()])

    assert len(sent) == len(result.attempts) == 2 and result.failure is None
    assert [attempt.error_stage for attempt in result.attempts] == ["schema", None]


async def test_snapshot_mismatch_makes_no_request() -> None:
    row, sent = await _run([], snapshot="b" * 40)

    assert sent == []
    assert (row["status"], row["error_code"], row["attempt"]) == ("failed", "llm_failed", 0)
    assert row["model"] == "configured-model"


async def test_timeout_is_stored_as_llm_timeout() -> None:
    timeout = httpx.ReadTimeout("timed out")
    row, sent = await _run([timeout, timeout])

    assert len(sent) == 2
    assert (row["status"], row["error_code"]) == ("failed", "llm_timeout")


async def test_request_over_the_input_byte_limit_is_stored_as_input_too_large() -> None:
    tiny = SETTINGS.model_copy(update={"llm_max_input_bytes": 10})
    row, sent = await _run([], settings=tiny)

    assert sent == []
    assert (row["status"], row["error_code"]) == ("failed", "input_too_large")


@pytest.mark.parametrize("proxy", [False, True], ids=["direct", "proxy"])
async def test_adapter_uses_the_url_and_token_selected_by_settings(proxy: bool) -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="direct-fixture-key",
        llm_default_model="configured-model",
        llm_timeout_seconds=1,
        llm_max_output_tokens=512,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
        proxy_token="proxy-fixture-key" if proxy else None,
        chat_proxy_url="https://proxy.example/namespace/v1/" if proxy else None,
        openai_model="configured-model" if proxy else None,
    ).require_llm()
    result, sent = await _run_result([_output()], settings=settings)

    assert result.failure is None and len(sent) == 1
    expected_url = "https://proxy.example/namespace/v1" if proxy else "https://api.openai.com/v1"
    expected_token = "proxy-fixture-key" if proxy else "direct-fixture-key"
    assert str(sent[0].url) == expected_url + "/responses"
    assert sent[0].headers["authorization"] == "Bearer " + expected_token
    assert json.loads(sent[0].content)["model"] == PROMPT.model
