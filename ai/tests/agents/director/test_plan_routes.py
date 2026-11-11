"""Controller가 허용한 생성 경로를 서로 섞지 않는 v17 producer schema."""

import importlib
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c


def runtime():
    return importlib.import_module("devon_ai.agents.director.runtime")


def context(option_count=0):
    parent = c.QuestionContract(
        "방법과 이유",
        (c.RequiredPoint("method", "방법"), c.RequiredPoint("reason", "이유")),
        (),
        (),
        "표시 질문 범위",
        ("project_understanding", "communication"),
    )
    options = (
        c.FollowUpOption("tech_lead", "t2", parent.evaluation_keys, ("reason",), "complete"),
        c.FollowUpOption("tech_lead", "t2", parent.evaluation_keys, ("method",), "clarify"),
    )[:option_count]
    return c.Context(
        "routes",
        "t2",
        3,
        9,
        (c.PersonaCount("hr_manager", 1), c.PersonaCount("tech_lead", 1)),
        ("tech_lead", "domain_lead"),
        (),
        (),
        (
            c.HistoryTurn("t1", "hr_manager", "역할은?", "학습했습니다.", None),
            c.HistoryTurn("t2", "tech_lead", "방법과 이유는?", "방법만 설명했습니다.", None),
        ),
        parent,
        (),
        (),
        c.ContextLimits(2, 0, "fixture"),
        evaluation_targets=(
            c.EvaluationTarget("tech_lead", ("technical_reasoning", "communication")),
            c.EvaluationTarget("domain_lead", ("communication",)),
        ),
        follow_up_options=options,
    )


def branch_props(branch):
    return branch["properties"], branch["properties"]["question_contract"]["properties"]


@pytest.mark.parametrize("option_count", [0, 1, 2])
def test_source_bound_routes_keep_each_controller_combination_atomic(option_count):
    ctx = context(option_count)
    before = asdict(ctx)
    schema = runtime()._source_bound_plan_schema(ctx, {}, True)
    branches = schema["properties"]["question"]["anyOf"]
    assert len(branches) == 2 + option_count
    seen = []
    for branch in branches:
        props, contract = branch_props(branch)
        assert branch["additionalProperties"] is False
        assert contract["assumptions"]["maxItems"] == 0
        (kind,) = props["question_type"]["enum"]
        (persona,) = props["persona"]["enum"]
        (parent,) = props["parent_turn_id"]["enum"]
        keys = contract["evaluation_keys"]["items"]["enum"]
        assert (
            contract["evaluation_keys"]["minItems"]
            == contract["evaluation_keys"]["maxItems"]
            == len(keys)
        )
        assert "uniqueItems" not in contract["evaluation_keys"]
        if kind == "main":
            assert parent is None
            target = next(target for target in ctx.evaluation_targets if target.persona == persona)
            assert keys == list(target.keys)
            assert contract["point_key"] == {"type": "string"}
        else:
            assert persona == "tech_lead" and parent == "t2"
            allowed = next(
                option
                for option in ctx.follow_up_options
                if list(option.missing_point_keys) == contract["point_key"]["enum"]
            )
            assert keys == list(allowed.evaluation_keys)
        seen.append(kind)
    assert seen.count("follow_up") == option_count
    assert asdict(ctx) == before


def test_only_registered_main_targets_and_allowed_personas_have_routes():
    ctx = replace(context(1), evaluation_targets=(context().evaluation_targets[1],))
    schema = runtime()._source_bound_plan_schema(ctx, {}, True)
    routes = [branch_props(branch) for branch in schema["properties"]["question"]["anyOf"]]
    assert [(p["persona"]["enum"], p["question_type"]["enum"]) for p, _ in routes] == [
        (["domain_lead"], ["main"]),
        (["tech_lead"], ["follow_up"]),
    ]
    assert all(props["parent_turn_id"]["enum"] != ["t1"] for props, _ in routes)


def test_zero_eligible_routes_fail_before_building_an_empty_anyof():
    ctx = replace(context(), evaluation_targets=())
    with pytest.raises(c.ContractError, match="source-bound allowed routes"):
        runtime()._source_bound_plan_schema(ctx, {}, True)
    schema = runtime()._source_bound_plan_schema(ctx, {}, False)
    branches = schema["properties"]["question"]["anyOf"]
    assert len(branches) == 2
    for branch in branches:
        _, contract = branch_props(branch)
        assert (
            contract["evaluation_keys"]["minItems"] == contract["evaluation_keys"]["maxItems"] == 0
        )
        assert "enum" not in contract["evaluation_keys"]["items"]


def test_source_bound_schema_does_not_mutate_legacy_bounded_schema():
    original = runtime()._bounded_plan_schema(context(), {}, True)
    before = deepcopy(original)
    runtime()._source_bound_plan_schema(context(2), {}, True)
    assert original == before == runtime()._bounded_plan_schema(context(), {}, True)


@pytest.mark.parametrize("change", ["keys", "point"])
def test_option_inconsistent_with_the_current_parent_is_not_a_producer_route(change):
    ctx = context(1)
    option = ctx.follow_up_options[0]
    option = replace(
        option,
        evaluation_keys=("technical_reasoning",) if change == "keys" else option.evaluation_keys,
        missing_point_keys=("other",) if change == "point" else option.missing_point_keys,
    )
    schema = runtime()._source_bound_plan_schema(
        replace(ctx, follow_up_options=(option,)), {}, True
    )
    branches = schema["properties"]["question"]["anyOf"]
    assert len(branches) == 2
    assert all(branch_props(branch)[0]["question_type"]["enum"] == ["main"] for branch in branches)
