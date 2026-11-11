"""발음 작업의 전송 범위와 한 번의 안전한 실패를 검사한다."""

import json

import httpx
import pytest
from devon_ai.contracts import AttemptMetadata, PromptSpec

from app.core.config import LLMSettings
from app.integrations.tts.pronunciation import SpeechFragment
from app.llm_tasks import question_pronunciation as pronunciation


@pytest.fixture
def settings() -> LLMSettings:
    return LLMSettings(
        openai_api_key="fixture-key",
        llm_base_url="https://mlapi.example.com/tenant/v1",
        llm_default_model="director-model",
        llm_timeout_seconds=50,
        llm_max_output_tokens=4096,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
        llm_reasoning_effort="high",
    )


@pytest.fixture
def prompt() -> PromptSpec:
    return PromptSpec(
        pronunciation.QUESTION_PRONUNCIATION_TASK,
        "question_pronunciation_v2@configured",
        "pronunciation-model",
        "Return pronunciation for each fragment.",
    )


def mock_provider(monkeypatch, status, output):
    requests = []
    call_model = pronunciation.call_model

    def transport(request):
        requests.append(request)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(
            status,
            json={
                "id": "pronunciation_fixture",
                "model": "actual-pronunciation-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
                "usage": {"input_tokens": 52, "output_tokens": 14},
            },
        )

    async def call_with_mock(*args, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            return await call_model(*args, **kwargs, http_client=client)

    monkeypatch.setattr(pronunciation, "call_model", call_with_mock)
    return requests


@pytest.mark.asyncio
async def test_sends_only_fragments_with_request_local_low_effort(monkeypatch, settings, prompt):
    output = json.dumps({"f2": "익스포넨셜 백오프", "f1": "서킷 브레이커"}, ensure_ascii=False)
    requests = mock_provider(monkeypatch, 200, output)
    attempts: list[AttemptMetadata] = []
    context = "발음 대상을 적용한 이유를 설명해 주세요."
    fragments = (
        SpeechFragment("circuit breaker", "term", context),
        SpeechFragment("exponential backoff", "term", context),
    )

    result = await pronunciation.pronounce_fragments(
        settings, prompt, fragments, attempt_sink=attempts
    )

    assert result == ("서킷 브레이커", "익스포넨셜 백오프")
    assert len(requests) == len(attempts) == 1
    request = requests[0]
    assert str(request.url) == "https://mlapi.example.com/tenant/v1/responses"
    assert request.extensions["timeout"]["read"] == 5.0
    body = json.loads(request.content)
    assert body["model"] == prompt.model
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 1024
    assert body["text"]["format"]["strict"] is True
    assert body["store"] is False
    assert json.loads(body["input"][0]["content"][0]["text"]) == {
        "fragments": {
            "f1": {"text": "circuit breaker", "kind": "term", "context": context},
            "f2": {"text": "exponential backoff", "kind": "term", "context": context},
        }
    }
    assert settings.llm_default_model == "director-model"
    assert settings.call_limits("director").reasoning_effort == "high"
    assert attempts[0].model == "actual-pronunciation-model"
    assert (attempts[0].input_tokens, attempts[0].output_tokens) == (52, 14)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "output", "stage"),
    [
        (503, "", "provider"),
        (429, "", "provider"),
        (200, '{"f1":"서킷 브레이커", "f1":"서킷"}', "parse"),
        (200, '{"wrong":"서킷 브레이커"}', "schema"),
        (200, '{"f1":"서킷 브레이커", "f2":"추가 항목"}', "schema"),
        (200, '{"f1":"raw-output-example"}', "semantic"),
    ],
)
async def test_invalid_output_or_provider_failure_has_no_retry(
    monkeypatch, settings, prompt, caplog, status, output, stage
):
    requests = mock_provider(monkeypatch, status, output)
    attempts: list[AttemptMetadata] = []
    caplog.set_level("INFO", logger=pronunciation.__name__)

    assert (
        await pronunciation.pronounce_fragments(
            settings,
            prompt,
            (SpeechFragment("circuit breaker", "term", "발음 대상을 적용해 주세요."),),
            attempt_sink=attempts,
        )
        is None
    )
    assert len(requests) == len(attempts) == 1
    assert attempts[0].error_stage == stage
    assert "question_pronunciation_fallback" in caplog.text
    assert "raw-output-example" not in caplog.text
    assert "circuit breaker" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fragments",
    [
        (),
        (SpeechFragment("https://example.com/users", "domain", "발음 대상"),),
        (SpeechFragment("api/v1/users", "path", "발음 대상"),),
        (SpeechFragment("circuit breaker를 설명해 주세요.", "term", "발음 대상"),),
        (SpeechFragment("hello world", "term", "발음 대상"),) * 13,
        (SpeechFragment("worker", "query", "발음 대상"),),
        (SpeechFragment("worker", "term", "가" * 241),),
        (SpeechFragment("worker", "term", "https://example.com?token=private"),),
        (SpeechFragment("worker", "term", "secret=private"),),
        (SpeechFragment("worker", "term", "contact@example.com"),),
        (SpeechFragment("worker", "term", "éé"),),
        (SpeechFragment("worker", "term", "발음 대상 \x00"),),
        (SpeechFragment("v2", "path", "발음 대상"),),
    ],
)
async def test_rejects_non_fragment_or_unbounded_input_before_http(
    monkeypatch, settings, prompt, fragments
):
    requests = mock_provider(monkeypatch, 503, "")
    assert await pronunciation.pronounce_fragments(settings, prompt, fragments) is None
    assert requests == []


@pytest.mark.asyncio
async def test_preserves_name_case_role_and_masked_context_per_identifier(
    monkeypatch, settings, prompt
):
    fragments = (
        SpeechFragment("AWS", "acronym", "발음 대상으로 배포한 이유를 설명해 주세요."),
        SpeechFragment("EventBus", "identifier", "발음 대상의 역할을 설명해 주세요."),
        SpeechFragment("message_queue", "path", "보호된 정보의 발음 대상 경로를 설명해 주세요."),
        SpeechFragment("my-api", "domain", "발음 대상 도메인으로 요청하는 과정을 설명해 주세요."),
        SpeechFragment("worker", "file", "발음 대상 파일의 역할을 설명해 주세요."),
        SpeechFragment(
            "toml", "extension", "발음 대상 확장자 파일을 사용하는 이유를 설명해 주세요."
        ),
    )
    expected = ("에이더블유에스", "이벤트 버스", "메시지 큐", "마이 에이피아이", "워커", "톰엘")
    output = json.dumps(
        {f"f{index}": spoken for index, spoken in enumerate(expected, start=1)}, ensure_ascii=False
    )
    requests = mock_provider(monkeypatch, 200, output)

    assert await pronunciation.pronounce_fragments(settings, prompt, fragments) == expected

    sent = json.loads(json.loads(requests[0].content)["input"][0]["content"][0]["text"])
    assert sent["fragments"] == {
        f"f{index}": {"text": part.text, "kind": part.kind, "context": part.context}
        for index, part in enumerate(fragments, start=1)
    }


@pytest.mark.parametrize("word", ["café", "cafe\u0301", "München", "Don't", "l’état"])
async def test_accepts_complete_latin_names_with_accents_and_apostrophes(
    monkeypatch, settings, prompt, word
):
    requests = mock_provider(monkeypatch, 200, '{"f1":"발음 이름"}')
    fragment = SpeechFragment(word, "term", "발음 대상을 설명하세요.")

    assert await pronunciation.pronounce_fragments(settings, prompt, (fragment,)) == ("발음 이름",)
    assert len(requests) == 1
