import asyncio
from dataclasses import fields

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import domain_category

PROMPT = c.PromptSpec("domain_category", "domain_category_v1", "fixture-model", "template")
LIMITS = c.CallLimits(10, 1000, 100_000, 100_000)


def _posting(**overrides: object) -> c.DomainPostingInput:
    values: dict[str, object] = {
        "position": "백엔드 개발자",
        "intro": "에누마는 글로벌 에듀테크 기업입니다.",
        "main_tasks": ("간편송금 서비스의 결제 API 개발",),
        "requirements": ("Python 3년 이상",),
        "preferred_points": ("여행을 좋아하는 분",),
    }
    values.update(overrides)
    return c.DomainPostingInput(**values)  # type: ignore[arg-type]


def _metadata(attempt: int = 1) -> c.AttemptMetadata:
    return c.AttemptMetadata(
        attempt, "fixture", "fixture-model", "domain_category_v1", "1", 2, None, 1
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


def _classify(provider: Provider, posting: c.DomainPostingInput | None = None, prompt=PROMPT):
    return asyncio.run(
        domain_category.classify_domain(
            posting or _posting(), prompt=prompt, limits=LIMITS, model_call=provider
        )
    )


def test_input_contract_has_no_company_fields() -> None:
    names = {item.name for item in fields(c.DomainPostingInput)}
    assert names == {"position", "intro", "main_tasks", "requirements", "preferred_points"}


def test_category_with_quoted_evidence_is_accepted_in_one_call() -> None:
    provider = Provider({"category": "finance", "evidence": "간편송금 서비스의  결제 API"})
    decision = _classify(provider)

    assert decision.category == "finance"
    assert decision.evidence == "간편송금 서비스의 결제 API"
    assert decision.failure is None
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert set(request.payload) == {
        "position",
        "intro",
        "main_tasks",
        "requirements",
        "preferred_points",
    }
    assert request.output_schema["properties"]["category"]["enum"] == list(
        domain_category.CATEGORIES
    )


def test_evidence_not_in_source_falls_back_to_etc_without_retry() -> None:
    provider = Provider({"category": "finance", "evidence": "국내 1위 은행"})
    decision = _classify(provider)

    assert decision.category == "etc"
    assert decision.evidence is None
    assert decision.failure is None
    assert len(provider.requests) == 1


def test_empty_evidence_for_non_etc_falls_back_to_etc() -> None:
    decision = _classify(Provider({"category": "travel", "evidence": "  "}))
    assert decision.category == "etc"


def test_etc_answer_keeps_etc() -> None:
    decision = _classify(Provider({"category": "etc", "evidence": ""}))
    assert (decision.category, decision.evidence, decision.failure) == ("etc", None, None)


@pytest.mark.parametrize(
    "response",
    [
        {"category": "education", "evidence": "에듀테크"},
        {"category": "finance"},
        {"category": "finance", "evidence": 1},
        ["finance"],
    ],
)
def test_schema_violation_is_failure_recorded_as_etc(response: object) -> None:
    decision = _classify(Provider(response))
    assert decision.category == "etc"
    assert decision.failure is not None and decision.failure.stage == "schema"
    assert len(decision.attempts) == 1


def test_provider_failure_is_recorded_as_etc() -> None:
    timeout = c.CallFailure("timeout", "llm_timeout", "timed out")
    decision = _classify(Provider(timeout))
    assert decision.category == "etc"
    assert decision.failure == timeout


def test_posting_without_text_does_not_call_model() -> None:
    provider = Provider()
    posting = _posting(
        position=None, intro=None, main_tasks=(), requirements=(), preferred_points=()
    )
    decision = _classify(provider, posting)
    assert (decision.category, decision.failure, decision.attempts) == ("etc", None, ())
    assert provider.requests == []


def test_wrong_prompt_task_is_rejected_before_call() -> None:
    provider = Provider()
    other = c.PromptSpec("jd_extract", "jd_extract_v1", "fixture-model", "template")
    decision = _classify(provider, prompt=other)
    assert decision.category == "etc"
    assert decision.failure is not None
    assert decision.failure.error_code == "domain_category_input_invalid"
    assert provider.requests == []
