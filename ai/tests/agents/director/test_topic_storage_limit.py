"""새 v17 생성만 DB의 50자 경계에 맞추고 보존 이력은 그대로 복원한다."""

import asyncio
import importlib
import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director.capabilities import prompt_capabilities
from devon_ai.agents.director.plan_wire import decode_plan_question

LONG_TOPIC = "postgres_deadlock_to_query_index_optimization_job_fit"
PROMPT = c.PromptSpec(
    "director",
    "director_v17@topic-boundary",
    "fixture-model",
    "## 공통\n근거 규칙\n## 질문 생성\n생성 지침\n## 독립 검토\n검토 지침\n",
)


def runtime():
    return importlib.import_module("devon_ai.agents.director.runtime")


def context():
    return c.Context(
        "topic-boundary",
        None,
        1,
        9,
        (),
        ("hr_manager",),
        (),
        (),
        (),
        None,
        (),
        (),
        c.ContextLimits(2, 0, "fixture"),
    )


def plan(topic_code):
    return {
        "question": {
            "persona": "hr_manager",
            "preamble": "",
            "request": "프로젝트에서 맡은 역할을 소개해 주세요.",
            "topic_code": topic_code,
            "question_contract": {
                "point_key": "role",
                "assumptions": [],
                "basis_refs": [],
                "evaluation_keys": [],
            },
            "evidence_refs": [],
            "jd_requirement_ids": [],
            "question_type": "main",
            "parent_turn_id": None,
        },
        "intent": "역할 확인",
        "reason_summary": "첫 자기소개에서 역할을 확인한다.",
    }


def review(version="director_v17@topic-boundary", *, status="asked"):
    result = {
        "plan_valid": True,
        "context_valid": True,
        "wording_valid": True,
        "contract_matches": True,
        "safe_alternative": True,
        "reason_summary": "현재 목적에 맞는다.",
    }
    capabilities = prompt_capabilities(version)
    if capabilities.required_point_review:
        receipt = {"status": status, "question_excerpt": "맡은 역할" if status == "asked" else None}
        result["point_coverage"] = (
            [{"key": "role", **receipt}] if capabilities.stable_point_review else {"role": receipt}
        )
    return result


class Provider:
    """실제 runtime 검증을 사용하며 공급자 호출만 메모리 입력으로 대체한다."""

    def __init__(self, raw, *, version=PROMPT.version, bypass=None):
        self.raw = raw
        self.version = version
        self.bypass = bypass
        self.requests = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        planning = request.payload["operation"] == "plan"
        raw = self.raw if planning else review(self.version)
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "fixture-model",
            request.prompt.version,
            request.schema_version,
            2,
            10,
            10,
            raw_output=json.dumps(raw, ensure_ascii=False),
        )
        try:
            if planning and self.bypass == "validator_not_called":
                # 검증기를 실행하지 않은 연결 계층도 최종 재검사를 통과할 수 없어야 한다.
                candidate = decode_plan_question(raw["question"], prompt_version=self.version)
                data = runtime()._Plan(candidate, raw["intent"], raw["reason_summary"])
            else:
                data = validator(raw)
                if planning and self.bypass == "validated_then_drifted":
                    data = replace(data, question=replace(data.question, topic_code=LONG_TOPIC))
        except c.ContractError as exc:
            return c.ModelResult(
                None, c.CallFailure(exc.stage, "llm_failed", "invalid"), (attempt,)
            )
        return c.ModelResult(data, None, (attempt,))


def run(provider, version=PROMPT.version):
    return asyncio.run(
        runtime().run_director(
            context(),
            prompt=replace(PROMPT, version=version),
            limits=c.CallLimits(1, 512, 65536, 65536),
            model_call=provider,
        )
    )


def test_v17_schema_limits_only_topic_code_without_mutating_shared_string_schemas():
    schema = runtime()._source_bound_plan_schema(context(), {}, False)
    (branch,) = schema["properties"]["question"]["anyOf"]
    fields = branch["properties"]
    assert fields["topic_code"] == {"type": "string", "maxLength": 50}
    for field in (
        fields["preamble"],
        fields["request"],
        fields["question_contract"]["properties"]["point_key"],
        schema["properties"]["intent"],
        schema["properties"]["reason_summary"],
    ):
        assert "maxLength" not in field
    assert (
        "maxLength"
        not in runtime()._plan_schema()["properties"]["question"]["properties"]["topic_code"]
    )


@pytest.mark.parametrize("character", ["a", "가", "🙂"])
@pytest.mark.parametrize("length", [50, 51])
def test_v17_accepts_50_characters_and_rejects_51_before_review(character, length):
    topic = character * length
    raw = plan(topic)
    provider = Provider(raw)
    result = run(provider)
    if length == 50:
        assert result.succeeded and result.data.question.data.topic_code == topic
        assert len(provider.requests) == 2
    else:
        assert result.failure is not None and result.data is None
        assert len(provider.requests) == 1
        assert provider.requests[0].payload["operation"] == "plan"
    assert raw["question"]["topic_code"] == topic


@pytest.mark.parametrize("bypass", ["validator_not_called", "validated_then_drifted"])
def test_v17_rechecks_storage_bound_after_provider_validation_or_bypass(bypass):
    provider = Provider(
        plan(LONG_TOPIC if bypass == "validator_not_called" else "role"), bypass=bypass
    )
    result = run(provider)
    assert result.failure is not None and result.failure.error_code == "director_candidate_invalid"
    assert result.data is None and len(provider.requests) == 1


@pytest.mark.parametrize("number", range(1, 17))
def test_old_producers_and_canonical_decoder_preserve_long_topic_codes(number):
    version = f"director_v{number}@preserved"
    raw = plan(LONG_TOPIC)
    canonical = decode_plan_question(raw["question"], prompt_version=PROMPT.version)
    raw["question"] = json.loads(json.dumps(asdict(canonical)))
    assert c.decode_strict(c.Question, raw["question"]).topic_code == LONG_TOPIC
    assert decode_plan_question(raw["question"], prompt_version=version) == canonical
    provider = Provider(raw, version=version)
    result = run(provider, version)
    assert result.succeeded and result.data.question.data.topic_code == LONG_TOPIC
    assert len(provider.requests) == 2
    assert (
        "maxLength"
        not in provider.requests[0].output_schema["properties"]["question"]["properties"][
            "topic_code"
        ]
    )


def test_historical_v17_plan_and_recovery_decoder_restore_long_topic_without_truncation():
    raw = plan(LONG_TOPIC)
    candidate = decode_plan_question(raw["question"], prompt_version=PROMPT.version)
    archived = [
        asdict(
            c.AttemptMetadata(
                number,
                "fixture",
                "fixture-model",
                PROMPT.version,
                schema,
                2,
                10,
                10,
                raw_output=json.dumps(output, ensure_ascii=False),
            )
        )
        for number, schema, output in (
            (1, "director-plan.v4", raw),
            (2, "director-review.v3", review(status="not_asked")),
        )
    ]
    saved = json.loads(json.dumps(archived))
    feedback = runtime().recovery_feedback_from_attempts(
        saved, failure_code="director_candidate_rewrite"
    )
    assert feedback is not None and feedback.previous_candidate == candidate
    assert feedback.previous_candidate.topic_code == LONG_TOPIC and len(LONG_TOPIC) == 53
    assert saved == archived
