import asyncio
from dataclasses import fields

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import domain_category

PROMPT = c.PromptSpec("domain_category", "domain_category_v2", "fixture-model", "template")
LIMITS = c.CallLimits(10, 1000, 100_000, 100_000)


def _posting(**overrides: object) -> c.DomainPostingInput:
    values: dict[str, object] = {
        "position": "백엔드 개발자",
        "intro": "에누마는 글로벌 에듀테크 기업입니다.\n\n아이들의 학습을 돕습니다.",
        "main_tasks": ("간편송금 서비스의\n결제 API 개발",),
        "requirements": ("Python 3년 이상",),
        "preferred_points": ("여행을 좋아하는 분",),
    }
    values.update(overrides)
    return c.DomainPostingInput(**values)  # type: ignore[arg-type]


def _metadata(attempt: int = 1, failure: c.CallFailure | None = None) -> c.AttemptMetadata:
    return c.AttemptMetadata(
        attempt,
        "fixture",
        "fixture-model",
        "domain_category_v2",
        "2",
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


def _classify(provider: Provider, posting: c.DomainPostingInput | None = None, prompt=PROMPT):
    return asyncio.run(
        domain_category.classify_domain(
            posting or _posting(), prompt=prompt, limits=LIMITS, model_call=provider
        )
    )


def test_input_contract_has_no_company_fields() -> None:
    names = {item.name for item in fields(c.DomainPostingInput)}
    assert names == {"position", "intro", "main_tasks", "requirements", "preferred_points"}


def test_payload_is_paragraphs_with_ids_and_text_kept_as_is() -> None:
    provider = Provider({"category": "etc", "evidence_id": None})
    _classify(provider)

    payload = provider.requests[0].payload
    assert list(payload) == list(domain_category.FIELDS)
    assert payload["intro"] == [
        {"id": "intro:0", "text": "에누마는 글로벌 에듀테크 기업입니다."},
        {"id": "intro:1", "text": "아이들의 학습을 돕습니다."},
    ]
    # 빈 줄이 아닌 줄바꿈은 문단 안에 그대로 둔다.
    assert payload["main_tasks"] == [
        {"id": "main_tasks:0", "text": "간편송금 서비스의\n결제 API 개발"}
    ]
    assert provider.requests[0].schema_version == "2"


def test_selected_id_is_restored_to_source_text_in_one_call() -> None:
    provider = Provider({"category": "finance", "evidence_id": "main_tasks:0"})
    decision = _classify(provider)

    assert decision.category == "finance"
    assert decision.evidence == "간편송금 서비스의\n결제 API 개발"
    assert decision.failure is None
    assert decision.attempts[0].error_stage is None
    assert len(provider.requests) == 1


def test_etc_with_null_id_is_success() -> None:
    decision = _classify(Provider({"category": "etc", "evidence_id": None}))
    assert (decision.category, decision.evidence, decision.failure) == ("etc", None, None)
    assert decision.attempts[0].error_stage is None


@pytest.mark.parametrize(
    "response",
    [
        {"category": "finance", "evidence_id": "main_tasks:9"},
        {"category": "finance", "evidence_id": "국내 1위 은행"},
        {"category": "finance", "evidence_id": None},
        {"category": "etc", "evidence_id": "intro:0"},
    ],
)
def test_wrong_evidence_id_is_semantic_failure_recorded_without_retry(response: object) -> None:
    provider = Provider(response)
    decision = _classify(provider)

    assert decision.category == "etc"
    assert decision.evidence is None
    assert decision.failure is not None and decision.failure.stage == "semantic"
    assert decision.attempts[0].error_stage == "semantic"
    assert decision.attempts[0].error_code == "llm_failed"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"category": "education", "evidence_id": "intro:0"},
        {"category": "finance"},
        {"category": "finance", "evidence": "간편송금"},
        {"category": "finance", "evidence_id": 1},
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
