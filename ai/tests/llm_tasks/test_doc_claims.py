import asyncio

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import doc_claims

PROMPT = c.PromptSpec("doc_claims", "doc_claims_v1", "fixture-model", "template")
LIMITS = c.CallLimits(10, 4000, 200_000, 100_000)
TEXT = (
    "프로젝트 A\n\n"
    "  Redis 캐시를 도입해 API 응답 시간을 70% 줄였습니다.  \r\n"
    "4인 팀에서 백엔드를 전담했습니다.\n"
)


def _claim(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "claim_text": "Redis 캐시를 도입해 API 응답 시간을 70% 줄였다.",
        "claim_type": "outcome",
        "tech_tags": ["Redis", "Redis"],
        "line_id": "L1",
    }
    item.update(overrides)
    return item


def _metadata(attempt: int, failure: c.CallFailure | None = None) -> c.AttemptMetadata:
    return c.AttemptMetadata(
        attempt,
        "fixture",
        "fixture-model",
        "doc_claims_v1",
        "1",
        2,
        None,
        1,
        error_stage=failure.stage if failure else None,
        error_code=failure.error_code if failure else None,
    )


class Provider:
    """BE gateway 대역. 응답마다 실제 validator를 실행하고, semantic이면 재시도하지 않는다."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[c.ModelRequest] = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        response = self.responses.pop(0)
        if type(response) is c.CallFailure:
            return c.ModelResult(None, response, (_metadata(len(self.requests), response),))
        try:
            data = validator(response)
        except c.ContractError as exc:
            failure = c.CallFailure(exc.stage, "llm_failed", "invalid")
            return c.ModelResult(None, failure, (_metadata(len(self.requests), failure),))
        return c.ModelResult(data, None, (_metadata(len(self.requests)),))


def _extract(provider: Provider, text: object = TEXT, prompt=PROMPT):
    return asyncio.run(
        doc_claims.extract_claims(text, prompt=prompt, limits=LIMITS, model_call=provider)  # type: ignore[arg-type]
    )


def test_payload_numbers_non_empty_lines_and_keeps_text_as_is() -> None:
    provider = Provider({"claims": []})
    _extract(provider)

    # 빈 줄만 빠지고, CRLF 줄도 나뉘며, 줄 양 끝 공백은 그대로다.
    assert provider.requests[0].payload == {
        "lines": [
            {"id": "L0", "text": "프로젝트 A"},
            {"id": "L1", "text": "  Redis 캐시를 도입해 API 응답 시간을 70% 줄였습니다.  "},
            {"id": "L2", "text": "4인 팀에서 백엔드를 전담했습니다."},
        ]
    }
    assert provider.requests[0].schema_version == "1"


def test_claims_are_returned_with_line_number_and_source_line() -> None:
    role = _claim(
        claim_text="4인 팀에서 백엔드를 전담했다.", claim_type="role", tech_tags=[], line_id="L2"
    )
    result = _extract(Provider({"claims": [_claim(), role]}))

    assert result.failure is None
    assert [claim.paragraph_no for claim in result.claims] == [1, 2]
    first = result.claims[0]
    assert first.claim_type == "outcome"
    assert first.tech_tags == ("Redis",)
    assert first.source_line == "  Redis 캐시를 도입해 API 응답 시간을 70% 줄였습니다.  "


def test_no_claims_is_success() -> None:
    result = _extract(Provider({"claims": []}))
    assert (result.claims, result.failure) == ((), None)
    assert result.attempts[0].error_stage is None


@pytest.mark.parametrize("line_id", ["L9", "1", "Redis 캐시를 도입해"])
def test_unknown_line_id_is_semantic_failure_without_retry(line_id: str) -> None:
    provider = Provider({"claims": [_claim(line_id=line_id)]})
    result = _extract(provider)

    assert result.claims == ()
    assert result.failure is not None and result.failure.stage == "semantic"
    assert result.attempts[0].error_stage == "semantic"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"claims": [_claim(claim_type="personality")]},
        {"claims": [_claim(claim_text="  ")]},
        {"claims": [_claim(tech_tags=["a", "b", "c", "d", "e", "f"])]},
        {"claims": [_claim(tech_tags=[""])]},
        {"claims": [_claim(line_id=1)]},
        {"claims": [{"claim_text": "x", "claim_type": "role", "tech_tags": []}]},
        {"claims": [_claim()] * (doc_claims.MAX_CLAIMS + 1)},
        {"claims": "none"},
        [],
    ],
)
def test_schema_violation_is_failure_with_no_claims(response: object) -> None:
    result = _extract(Provider(response))
    assert result.claims == ()
    assert result.failure is not None and result.failure.stage == "schema"


def test_provider_failure_returns_no_claims() -> None:
    timeout = c.CallFailure("timeout", "llm_timeout", "timed out")
    result = _extract(Provider(timeout))
    assert (result.claims, result.failure) == ((), timeout)


def test_blank_document_does_not_call_model() -> None:
    provider = Provider()
    result = _extract(provider, " \n\n \n")
    assert (result.claims, result.failure, result.attempts) == ((), None, ())
    assert provider.requests == []


@pytest.mark.parametrize(
    ("text", "prompt"),
    [
        (TEXT, c.PromptSpec("domain_category", "domain_category_v1", "fixture-model", "t")),
        (TEXT, c.PromptSpec("doc_claims", "doc_claims_v2", "fixture-model", "t")),
        (None, PROMPT),
    ],
)
def test_invalid_input_is_rejected_before_call(text: object, prompt: c.PromptSpec) -> None:
    provider = Provider()
    result = _extract(provider, text, prompt)
    assert result.failure is not None
    assert result.failure.error_code == "doc_claims_input_invalid"
    assert provider.requests == []
