"""현재 .env에서 L1까지 이어지는 점검 명령을 가짜 HTTP 공급자로 검증한다."""

import json

import httpx
import pytest

from app.core.config import get_settings


@pytest.mark.parametrize("status", [200, 401])
async def test_check_reads_env_and_calls_l1_without_rewriting_requests(
    tmp_path, monkeypatch, status
):
    from scripts import check_llm

    names = (
        "PROXY_TOKEN",
        "CHAT_PROXY_URL",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
        "LLM_DEFAULT_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_MAX_INPUT_BYTES",
        "LLM_MAX_RESPONSE_BYTES",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PROXY_TOKEN=private-fixture\nCHAT_PROXY_URL=https://proxy.example/tenant/v1\n"
        "OPENAI_MODEL=env-model\nLLM_TIMEOUT_SECONDS=5\nLLM_MAX_OUTPUT_TOKENS=1024\n"
        "LLM_MAX_INPUT_BYTES=32768\nLLM_MAX_RESPONSE_BYTES=131072\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    sent = []

    def transport(request):
        sent.append(request)
        assert str(request.url) == "https://proxy.example/tenant/v1/responses"
        assert request.headers["Authorization"] == "Bearer private-fixture"
        body = json.loads(request.content)
        assert body["model"] == "env-model"
        repo = json.loads(body["input"][0]["content"][0]["text"])["repositories"][0]
        item = {
            "repository_id": repo["repository_id"],
            "head_sha": repo["head_sha"],
            "purpose": "합성 작업 목록",
            "key_features": ["작업 저장"],
            "project_types": ["cli"],
            "tech_stack": ["Python"],
            "project_role_summary": "로컬 작업 목록 관리",
            "basis": [{"kind": "readme", "claim": "작업 목록을 관리함"}],
            "limitations": ["실제 실행과 개인 기여 미확인"],
        }
        return httpx.Response(
            status,
            json={
                "id": "resp_fixture",
                "model": "env-model-snapshot",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"repositories": [item]})}
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 60},
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        check_llm.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    try:
        result = await check_llm.check_connection()
    finally:
        get_settings.cache_clear()
    assert result["success"] is (status == 200)
    assert len(sent) == 1
    assert result["succeeded_items"] == (1 if status == 200 else 0)
    assert result["database_written"] is False
    assert "private-fixture" not in json.dumps(result)
    assert "proxy.example" not in json.dumps(result)


def test_cli_configuration_failure_does_not_print_exception_details(monkeypatch, capsys):
    from scripts import check_llm

    async def fail():
        raise ValueError("private-token https://private.example/namespace")

    monkeypatch.setattr(check_llm, "check_connection", fail)
    assert check_llm.main() == 1
    output = capsys.readouterr()
    assert "private" not in output.out + output.err


@pytest.mark.parametrize("stage", ["budget", "semantic"])
async def test_check_reports_failure_without_a_failed_provider_attempt(monkeypatch, stage):
    from types import SimpleNamespace

    from app.core.config import LLMSettings
    from scripts import check_llm
    from tests.llm_tasks.test_repo_shallow import _batch, _item, _response

    settings = LLMSettings(
        openai_api_key="fixture-key",
        llm_default_model="env-model",
        llm_timeout_seconds=5,
        llm_max_output_tokens=1024,
        llm_max_input_bytes=1 if stage == "budget" else 32768,
        llm_max_response_bytes=131072,
    )
    monkeypatch.setattr(
        check_llm, "get_settings", lambda: SimpleNamespace(require_llm=lambda: settings)
    )
    sent = []

    def transport(request):
        sent.append(request)
        repo = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])[
            "repositories"
        ][0]
        return httpx.Response(
            200, json=_response(_batch(_item(repo["repository_id"], head_sha="b" * 40)))
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        check_llm.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    result = await check_llm.check_connection()
    assert result["success"] is False
    if stage == "budget":
        assert sent == []
        assert result["batch_failure"]["stage"] == "budget"
    else:
        assert len(sent) == 1
        assert result["item_failures"][0]["stage"] == "semantic"
        assert result["attempts"][0]["error_stage"] is None
