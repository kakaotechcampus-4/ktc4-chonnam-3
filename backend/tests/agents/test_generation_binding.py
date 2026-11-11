"""재생성은 최초 typed 입력의 동일성만 확인하며 모델 원문을 상태에 복제하지 않는다."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from devon_ai import contracts as c

from tests.agents.test_director_input_budget import fixture


def inputs():
    context, previous = fixture()
    return dict(
        context=context,
        prompt=c.PromptSpec("director", "director_v12", "logical-model", "private-policy-body"),
        answer_analysis=previous["turn-8"],
        prior_analyses=previous,
        reference_texts={c.BasisRef("jd_requirement", "jd"): "actual full source"},
        lookup_summary="조회하지 않은 범위는 미확인",
        tool_results=(
            c.ToolResult("not_found", (), ("repo@ref/source",), ("원문 추가 없음",), None),
        ),
    )


def api():
    from app.features.interview import generation_binding

    return generation_binding


def test_capture_only_hashes_and_prompt_identity_and_preserves_existing_state():
    values = inputs()
    original = {"other_state": {"keep": [1, 2]}}
    before = deepcopy(original)
    call = uuid4()
    state = api().capture(original, call_id=call, **values)
    assert original == before and state["other_state"] == original["other_state"]
    saved = state[api().STATE_KEY][str(call)]
    assert set(saved) == {"target", "binding", "prompt"}
    assert set(saved["prompt"]) == {"task_name", "version", "model", "template_sha256"}
    text = json.dumps(saved, ensure_ascii=False)
    assert "private-policy-body" not in text and "actual full source" not in text
    assert values["context"].history[0].answer not in text
    assert api().matches(state, call_id=call, **values)
    assert api().capture(state, call_id=call, **values) == state


@pytest.mark.parametrize(
    "change",
    [
        "answer",
        "evidence",
        "analysis",
        "past",
        "source",
        "tool",
        "lookup",
        "version",
        "model",
        "template",
    ],
)
def test_every_generation_dependency_must_still_match(change):
    values = inputs()
    call = uuid4()
    state = api().capture({}, call_id=call, **values)
    mutated = dict(values)
    if change == "answer":
        history = values["context"].history
        mutated["context"] = replace(
            values["context"], history=(replace(history[0], answer="정정 발언"), *history[1:])
        )
    elif change == "evidence":
        evidence = values["context"].evidence
        mutated["context"] = replace(
            values["context"],
            evidence=(replace(evidence[0], content="changed code"), *evidence[1:]),
        )
    elif change == "analysis":
        mutated["answer_analysis"] = values["prior_analyses"]["turn-7"]
    elif change == "past":
        mutated["prior_analyses"] = {
            k: v for k, v in values["prior_analyses"].items() if k != "turn-1"
        }
    elif change == "source":
        mutated["reference_texts"] = {c.BasisRef("jd_requirement", "jd"): "updated source"}
    elif change == "tool":
        mutated["tool_results"] = ()
    elif change == "lookup":
        mutated["lookup_summary"] = "different lookup result"
    else:
        mutated["prompt"] = replace(values["prompt"], **{change: "different"})
    assert not api().matches(state, call_id=call, **mutated)
    with pytest.raises(ValueError):
        api().capture(state, call_id=call, **mutated)


@pytest.mark.parametrize("change", ["missing", "unknown", "target", "prompt", "digest", "extra"])
def test_missing_or_mutated_record_is_not_a_binding(change):
    values = inputs()
    call = uuid4()
    state = api().capture({}, call_id=call, **values)
    if change == "missing":
        state = {}
    elif change == "unknown":
        call = uuid4()
    else:
        saved = state[api().STATE_KEY][str(call)]
        if change == "target":
            saved["target"] = True
        elif change == "prompt":
            saved["prompt"]["template_sha256"] = "0" * 64
        elif change == "digest":
            saved["binding"] = "0" * 64
        else:
            saved["unexpected"] = "not allowed"
    assert not api().matches(state, call_id=call, **values)


def test_three_slots_each_of_eight_next_question_targets_are_the_finite_ceiling():
    values = inputs()
    state = {}
    for target in range(2, 10):
        context = replace(values["context"], turn_no=target)
        for _ in range(3):
            state = api().capture(state, call_id=uuid4(), **{**values, "context": context})
    assert len(state[api().STATE_KEY]) == 24
    with pytest.raises(ValueError):
        api().capture(state, call_id=uuid4(), **values)


def test_input_order_does_not_change_identity_but_past_values_do():
    values = inputs()
    first = api().fingerprint(**values)
    assert first == api().fingerprint(
        **{**values, "prior_analyses": dict(reversed(list(values["prior_analyses"].items())))}
    )
    assert len(first) == 64 and asdict(values["prompt"])["template"] == "private-policy-body"


def test_fourth_round_for_one_target_is_rejected_even_below_global_limit():
    values, state = inputs(), {}
    for _ in range(3):
        state = api().capture(state, call_id=uuid4(), **values)
    with pytest.raises(ValueError):
        api().capture(state, call_id=uuid4(), **values)


def test_first_question_is_outside_the_after_answer_binding_scope():
    values = inputs()
    with pytest.raises(ValueError):
        api().capture(
            {}, call_id=uuid4(), **{**values, "context": replace(values["context"], turn_no=1)}
        )
