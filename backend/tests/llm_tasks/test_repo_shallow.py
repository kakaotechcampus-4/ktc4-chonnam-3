"""L1 BE 연결: 가짜 HTTP 공급자로 호출 상한과 repo_analyses 행 매핑을 검사한다. DB는 쓰지 않는다."""

import json
import uuid

import httpx
from devon_ai import contracts as c
from pydantic import SecretStr

from app.core.config import LLMSettings
from app.llm_tasks import repo_shallow

SHA = "a" * 40
REPO_1 = str(uuid.UUID(int=1))
REPO_2 = str(uuid.UUID(int=2))
REPO_3 = str(uuid.UUID(int=3))
PROMPT = c.PromptSpec("repo_shallow", "repo_shallow_v1", "configured-model", "fixture prompt")
SETTINGS = LLMSettings(
    openai_api_key=SecretStr("fixture-key"),
    llm_default_model="configured-model",
    llm_timeout_seconds=1,
    llm_max_output_tokens=512,
    llm_max_input_bytes=65536,
    llm_max_response_bytes=65536,
)


def _input(repository_id: str) -> c.ShallowRepoInput:
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


def _item(repository_id: str, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "repository_id": repository_id,
        "head_sha": SHA,
        "purpose": "캐시 서비스",
        "key_features": ["캐시 조회"],
        "project_types": ["backend"],
        "tech_stack": ["Python", "Redis"],
        "project_role_summary": "캐시 기능을 제공하는 프로젝트",
        "basis": [{"kind": "readme", "claim": "캐시 서비스를 제공함"}],
        "limitations": ["실행 동작 미확인"],
    }
    item.update(overrides)
    return item


def _response(text: str) -> dict[str, object]:
    return {
        "id": "resp_repo_shallow_fixture",
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


def _batch(*items: dict[str, object]) -> str:
    return json.dumps({"repositories": list(items)}, ensure_ascii=False)


def _transport(replies: list[object], sent: list[httpx.Request]) -> httpx.MockTransport:
    pending = iter(replies)

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        reply = next(pending)
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json=_response(str(reply)))

    return httpx.MockTransport(handle)


async def _run(replies: list[object], *inputs: c.ShallowRepoInput):
    sent: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_transport(replies, sent)) as http:
        result = await repo_shallow.analyze_repositories(
            inputs, prompt=PROMPT, settings=SETTINGS, http_client=http
        )
    return result, sent


async def test_successful_batch_maps_each_repository_to_a_row() -> None:
    raw = _batch(_item(REPO_2), _item(REPO_1))
    result, sent = await _run([raw], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 1
    body = json.loads(sent[0].content)
    assert body["model"] == "configured-model" and body["max_output_tokens"] == 512
    assert [row["repository_id"] for row in rows] == [uuid.UUID(REPO_1), uuid.UUID(REPO_2)]
    assert rows[0] == {
        "repository_id": uuid.UUID(REPO_1),
        "analysis_level": "l1",
        "head_sha": SHA,
        "prompt_version": "repo_shallow_v1",
        "model": "actual-model-snapshot",
        "status": "succeeded",
        "error_code": None,
        "batch_position": 0,
        # 프로젝트 요약의 저장 필드는 BE 합의 전이라 비우고 result에만 둔다.
        "summary": None,
        "tech_stack": ["Python", "Redis"],
        "notable_areas": None,
        "result": rows[0]["result"],
        "raw_output": raw,
        "input_tokens": 100,
        "output_tokens": 60,
        "latency_ms": rows[0]["latency_ms"],
        "attempt": 1,
    }
    assert rows[0]["result"]["project_role_summary"] == "캐시 기능을 제공하는 프로젝트"
    assert rows[1]["batch_position"] == 1


async def test_l1_passes_configured_proxy_and_keeps_prompt_model() -> None:
    settings = SETTINGS.model_copy(
        update={
            "llm_base_url": "https://proxy.example/tenant/v1",
            "openai_api_key": SecretStr("proxy-fixture"),
            "llm_default_model": "different-registration-default",
        }
    )
    sent: list[httpx.Request] = []
    async with httpx.AsyncClient(transport=_transport([_batch(_item(REPO_1))], sent)) as http:
        run = await repo_shallow.analyze_repositories(
            (_input(REPO_1),), prompt=PROMPT, settings=settings, http_client=http
        )
    assert run.result.succeeded
    assert len(sent) == 1
    assert str(sent[0].url) == "https://proxy.example/tenant/v1/responses"
    assert sent[0].headers["Authorization"] == "Bearer proxy-fixture"
    assert json.loads(sent[0].content)["model"] == PROMPT.model


async def test_schema_failed_repository_is_retried_once_and_stored_as_success() -> None:
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=3))
    result, sent = await _run([first, _batch(_item(REPO_2))], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 2
    assert [row["status"] for row in rows] == ["succeeded", "succeeded"]
    # 각 행의 호출 기록은 그 저장소 결과를 실제로 만든 시도의 값이다.
    assert [(row["attempt"], row["raw_output"]) for row in rows] == [
        (1, first),
        (2, _batch(_item(REPO_2))),
    ]


async def test_one_budget_caps_the_whole_task_at_two_http_requests() -> None:
    # 첫 호출이 parse 재시도로 2회를 쓰면 부분 실패가 있어도 재요청하지 않는다.
    partial = _batch(_item(REPO_1), _item(REPO_2, purpose=3))
    result, sent = await _run(["not-json", partial], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 2
    assert [(row["status"], row["error_code"]) for row in rows] == [
        ("succeeded", None),
        ("failed", "llm_failed"),
    ]


async def test_semantic_failure_is_stored_without_retry_or_default_values() -> None:
    raw = _batch(_item(REPO_1, head_sha="b" * 40))
    result, sent = await _run([raw], _input(REPO_1))
    (row,) = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1),), PROMPT)

    assert len(sent) == 1
    assert row["status"] == "failed" and row["error_code"] == "llm_failed"
    assert row["summary"] is None and row["tech_stack"] == [] and row["result"] is None


async def test_whole_call_timeout_fails_every_repository_with_llm_timeout() -> None:
    timeout = httpx.ReadTimeout("timed out")
    result, sent = await _run([timeout, timeout], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 2
    assert [(row["status"], row["error_code"]) for row in rows] == [
        ("failed", "llm_timeout"),
        ("failed", "llm_timeout"),
    ]
    assert rows[0]["model"] == "configured-model"


async def test_rejected_input_makes_no_request_and_uses_a_known_error_code() -> None:
    result, sent = await _run([], _input(REPO_1), _input(REPO_1))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1),), PROMPT)

    assert sent == []
    assert rows[0]["error_code"] == "llm_failed" and rows[0]["attempt"] == 0


async def test_request_over_the_input_byte_limit_is_stored_as_input_too_large() -> None:
    sent: list[httpx.Request] = []
    tiny = SETTINGS.model_copy(update={"llm_max_input_bytes": 10})
    async with httpx.AsyncClient(transport=_transport([], sent)) as http:
        result = await repo_shallow.analyze_repositories(
            (_input(REPO_1),), prompt=PROMPT, settings=tiny, http_client=http
        )
    (row,) = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1),), PROMPT)

    assert sent == []
    assert row["status"] == "failed" and row["error_code"] == "input_too_large"


async def test_failed_row_keeps_the_attempt_that_actually_failed_it() -> None:
    # repo-3 은 첫 호출에서 semantic 실패, repo-2 는 재요청에서도 schema 실패한다.
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=3), _item(REPO_3, head_sha="b" * 40))
    retry = _batch(_item(REPO_2, purpose=4))
    inputs = (_input(REPO_1), _input(REPO_2), _input(REPO_3))
    result, sent = await _run([first, retry], *inputs)
    rows = repo_shallow.to_repo_analysis_rows(result, inputs, PROMPT)

    assert len(sent) == 2
    assert [(row["status"], row["attempt"], row["raw_output"]) for row in rows] == [
        ("succeeded", 1, first),
        ("failed", 2, retry),
        ("failed", 1, first),
    ]


async def test_repository_missing_from_output_keeps_the_first_call_record() -> None:
    # repo-3 은 첫 응답에서 빠졌다(재요청 대상 아님). repo-2 재요청 때문에 시도가 2회가 된다.
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=3))
    inputs = (_input(REPO_1), _input(REPO_2), _input(REPO_3))
    result, sent = await _run([first, _batch(_item(REPO_2))], *inputs)
    rows = repo_shallow.to_repo_analysis_rows(result, inputs, PROMPT)

    assert len(sent) == 2
    assert (rows[2]["status"], rows[2]["attempt"], rows[2]["raw_output"]) == ("failed", 1, first)


DEEP = "[" * 10_000 + "0" + "]" * 10_000


async def test_deeply_nested_whole_parse_failure_still_returns_rows() -> None:
    # Gateway가 parse 실패로 거절한 원문을 행 변환에서 다시 해석하지 않는다.
    result, sent = await _run([DEEP, DEEP], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 2
    assert [(row["status"], row["error_code"], row["attempt"]) for row in rows] == [
        ("failed", "llm_parse_failed", 2),
        ("failed", "llm_parse_failed", 2),
    ]


async def test_deeply_nested_retry_keeps_first_success_rows() -> None:
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=3))
    result, sent = await _run([first, DEEP], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert len(sent) == 2
    # 재요청이 통째로 실패하면 repo-2 결과는 첫 호출의 schema 실패 그대로다.
    assert [(row["status"], row["attempt"], row["raw_output"]) for row in rows] == [
        ("succeeded", 1, first),
        ("failed", 1, first),
    ]


async def test_retry_omitting_the_repository_records_the_retry_attempt() -> None:
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=""))
    retry = _batch()
    result, _ = await _run([first, retry], _input(REPO_1), _input(REPO_2))
    rows = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1), _input(REPO_2)), PROMPT)

    assert (rows[1]["status"], rows[1]["attempt"], rows[1]["raw_output"]) == ("failed", 2, retry)


async def test_timeout_after_whole_schema_failure_records_the_timeout_attempt() -> None:
    timeout = httpx.ReadTimeout("timed out")
    # 최상위에 repositories 외 키가 있으면 호출 전체가 schema 실패다. 원문에는 repo-1 ID가 있다.
    whole_schema = json.dumps({"repositories": [_item(REPO_1)], "extra": 1})
    result, _ = await _run([whole_schema, timeout], _input(REPO_1))
    (row,) = repo_shallow.to_repo_analysis_rows(result, (_input(REPO_1),), PROMPT)

    assert (row["error_code"], row["attempt"], row["raw_output"]) == ("llm_timeout", 2, None)


async def test_unrequested_repository_in_retry_keeps_its_first_record() -> None:
    # repo-3 은 첫 호출에서 semantic 실패해 재요청 대상이 아니다. 재응답에 끼어도 첫 호출 기록이다.
    first = _batch(_item(REPO_1), _item(REPO_2, purpose=3), _item(REPO_3, head_sha="b" * 40))
    retry = _batch(_item(REPO_2), _item(REPO_3))
    inputs = (_input(REPO_1), _input(REPO_2), _input(REPO_3))
    result, _ = await _run([first, retry], *inputs)
    rows = repo_shallow.to_repo_analysis_rows(result, inputs, PROMPT)

    assert [(row["status"], row["attempt"]) for row in rows] == [
        ("succeeded", 1),
        ("succeeded", 2),
        ("failed", 1),
    ]
    assert rows[2]["raw_output"] == first
