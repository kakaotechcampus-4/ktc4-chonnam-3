"""Accepted v2의 원문 보존·version 경계를 팀원 회귀와 별도로 검사한다."""

import asyncio

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks.domain_category import classify_domain

PROMPT = c.PromptSpec("domain_category", "domain_category_v2", "fixture-model", "template")
LIMITS = c.CallLimits(1, 200, 20_000, 20_000)


def _run(posting, *, prompt=PROMPT):
    requests = []

    async def model_call(request, validator):
        requests.append(request)
        # 분류 의미의 정답이 아니라 ID에서 회수하는 원문을 검사하는 대역이다.
        data = validator({"category": "mobility", "evidence_id": "main_tasks:0"})
        attempt = c.AttemptMetadata(
            1, "fixture", "fixture-model", request.prompt.version, request.schema_version, 1, 2, 1
        )
        return c.ModelResult(data, None, (attempt,))

    decision = asyncio.run(
        classify_domain(posting, prompt=prompt, limits=LIMITS, model_call=model_call)
    )
    return decision, requests


@pytest.mark.parametrize("version", ["domain_category_v1", "domain_category_v3"])
def test_non_v2_prompt_is_rejected_before_any_model_call(version):
    posting = c.DomainPostingInput(None, None, ("차량 시험 도구",), (), ())
    decision, requests = _run(posting, prompt=c.PromptSpec("domain_category", version, "m", "t"))

    assert decision.failure is not None
    assert decision.failure.stage == "schema"
    assert decision.failure.error_code == "domain_category_input_invalid"
    assert decision.attempts == ()
    assert requests == []


@pytest.mark.parametrize(
    "source",
    [
        "  차량 보안 시험 도구  ",
        "\t차량 데이터 \u200b분석\n도구\t",
        "  ++/Qt 차량 시험\n도구  ",
        "차량 제어기\r\n시험 도구 ",
    ],
)
def test_selected_paragraph_keeps_edges_newlines_and_characters(source):
    decision, requests = _run(c.DomainPostingInput(None, None, (source,), (), ()))

    assert decision.failure is None
    assert decision.evidence is not None and decision.evidence.encode() == source.encode()
    assert requests[0].payload["main_tasks"] == [{"id": "main_tasks:0", "text": source}]


def test_blank_lines_preserve_paragraph_bytes_and_continue_ids_across_array_items():
    first = "  첫 문단\r\n같은 문단  "
    second = "둘째 문단 "
    third = " 셋째 문단 "
    posting = c.DomainPostingInput(
        None, None, (first + "\r\n \t\r\n\r\n" + second + "\n\n", third), (), ()
    )
    decision, requests = _run(posting)

    assert decision.evidence == first
    assert requests[0].payload == {
        "position": [],
        "intro": [],
        "main_tasks": [
            {"id": "main_tasks:0", "text": first},
            {"id": "main_tasks:1", "text": second},
            {"id": "main_tasks:2", "text": third},
        ],
        "requirements": [],
        "preferred_points": [],
    }


def test_same_id_is_always_restored_from_the_current_request_source():
    for source in ("차량 제어기 시험 도구", "다른 공고의 차량 보안 도구"):
        decision, _ = _run(c.DomainPostingInput(None, None, (source,), (), ()))
        assert decision.evidence == source
