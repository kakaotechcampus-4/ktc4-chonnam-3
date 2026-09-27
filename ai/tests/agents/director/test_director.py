import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import agent


@pytest.fixture
def context():
    return c.Context(
        "interview-1",
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


@pytest.fixture
def contract():
    return c.QuestionContract(
        "본인의 역할 소개",
        (c.RequiredPoint("role", "본인 역할"),),
        (),
        (),
        "역할 소개",
    )


def candidate(contract, **changes):
    return replace(
        c.Question("hr_manager", "맡은 역할을 소개해 주세요.", "role", contract, (), ()), **changes
    )


def model_output(question):
    data = asdict(question)
    del data["question_contract"]
    return data


def metadata():
    return c.AttemptMetadata(1, "fixture", "fixture-model", "director_v1", "2", 2, None, 12)


class Provider:
    """External model stand-in; parsing/policy validators are real production functions."""

    def __init__(self, output):
        self.output = json.loads(json.dumps(output))
        self.requests = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        try:
            data = validator(self.output)
        except c.ContractError as exc:
            return c.ModelResult(
                None, c.CallFailure(exc.stage, "llm_failed", "invalid"), (metadata(),)
            )
        return c.ModelResult(data, None, (metadata(),))


async def approved_review(request, question):
    # Synthetic independent assessment for this exact candidate; not a production reviewer.
    return c.QuestionReview(
        question.text,
        c.decode(c.QuestionContract, json.loads(json.dumps(request.payload["question_contract"]))),
    )


def generate(context, contract, provider, **options):
    review = options.pop("review", approved_review)
    limits = options.pop("limits", c.CallLimits(1, 512, 65536, 65536))
    return asyncio.run(
        agent.generate_question(
            context,
            contract,
            prompt=c.PromptSpec("director", "director_v1", "fixture-model", "draft"),
            limits=limits,
            model_call=provider,
            review=review,
            **options,
        )
    )


def test_first_hr_question_returns_checked_data_and_preserves_attempts(context, contract):
    provider = Provider(model_output(candidate(contract)))
    before = asdict(context)
    result = generate(context, contract, provider)
    assert result.succeeded
    assert result.data.data.text == "맡은 역할을 소개해 주세요."
    assert result.data.data.question_contract is contract
    assert c.to_data(result.data)["question_contract"]["purpose"] == "본인의 역할 소개"
    assert result.attempts == (metadata(),)
    assert asdict(context) == before
    request = provider.requests[0]
    assert request.prompt.task_name == "director"
    assert request.payload["question_contract"]["purpose"] == "본인의 역할 소개"
    assert request.payload["answer_analysis"] is None
    assert request.payload["reference_texts"] == []
    assert request.schema_version == "2"


def test_model_contract_echo_is_schema_failure_before_review(context, contract):
    raw = model_output(candidate(contract))
    raw["question_contract"] = asdict(contract)

    async def forbidden(*args):
        pytest.fail("output with an unowned contract reached reviewer")

    result = generate(context, contract, Provider(raw), review=forbidden)
    assert result.failure.stage == "schema" and result.data is None


@pytest.mark.parametrize("field", ["evidence_refs", "jd_requirement_ids"])
def test_model_reference_fields_must_be_json_lists(context, contract, field):
    raw = model_output(candidate(contract))
    raw[field] = "not-a-list"
    result = generate(context, contract, Provider(raw))
    assert result.failure.stage == "schema" and result.data is None


def technical_context(context):
    evidence = c.Evidence(
        "ev-1", "repo-1", "a" * 40, "source_file", "cache.py", None, "cache code", None
    )
    return replace(
        context,
        current_turn_id="answered-turn-1",
        turn_no=2,
        allowed_personas=("tech_lead",),
        persona_counts=(c.PersonaCount("hr_manager", 1),),
        repositories=(c.ContextRepository("repo-1", "a" * 40, True, ("l2-1",), ()),),
        evidence=(evidence,),
        jd_requirements=(
            c.JDRequirement("jd-1", "캐시 설계", "required", "requirements", ("Redis",)),
        ),
        history=(
            c.HistoryTurn(
                "answered-turn-1", "hr_manager", "역할?", "캐시를 담당했습니다.", "analysis-1"
            ),
        ),
    )


def test_followup_uses_real_source_text_and_injected_reviewer(context, contract):
    context = technical_context(context)
    contract = replace(
        contract,
        basis_refs=(
            c.BasisRef("evidence", "ev-1"),
            c.BasisRef("jd_requirement", "jd-1"),
            c.BasisRef("answer_turn", "answered-turn-1"),
        ),
    )
    question = candidate(
        contract, persona="tech_lead", evidence_refs=("ev-1",), jd_requirement_ids=("jd-1",)
    )
    provider = Provider(model_output(question))
    reviewed = []

    async def review(request, actual_question):
        reviewed.append((request.payload["context"], actual_question))
        return c.QuestionReview(actual_question.text, contract)

    result = generate(context, contract, provider, review=review)
    assert result.succeeded
    assert reviewed == [(asdict(context), question)]
    texts = provider.requests[0].payload["reference_texts"]
    assert {"kind": "evidence", "id": "ev-1", "text": "cache code"} in texts
    assert {"kind": "answer_turn", "id": "answered-turn-1", "text": "캐시를 담당했습니다."} in texts


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_refs": ("ev-2",)},
        {"jd_requirement_ids": ("jd-2",)},
    ],
)
def test_candidate_references_stay_within_prepared_plan(context, contract, change):
    context = technical_context(context)
    context = replace(
        context,
        evidence=(
            *context.evidence,
            c.Evidence(
                "ev-2", "repo-1", "a" * 40, "source_file", "queue.py", None, "queue code", None
            ),
        ),
        jd_requirements=(
            *context.jd_requirements,
            c.JDRequirement("jd-2", "메시지 큐", "preferred", "preferred", ("Kafka",)),
        ),
    )
    contract = replace(
        contract,
        basis_refs=(
            c.BasisRef("evidence", "ev-1"),
            c.BasisRef("jd_requirement", "jd-1"),
        ),
    )

    async def forbidden(*args):
        pytest.fail("reference outside the prepared plan reached reviewer")

    result = generate(
        context,
        contract,
        Provider(model_output(candidate(contract, persona="tech_lead", **change))),
        review=forbidden,
    )
    assert result.failure.stage == "semantic" and result.data is None


@pytest.mark.parametrize(
    "change",
    [
        {"persona": "tech_lead"},
        {"evidence_refs": ("unknown",)},
        {"jd_requirement_ids": ("unknown",)},
    ],
)
def test_invalid_candidate_is_rejected_before_review(context, contract, change):
    async def forbidden(*args):
        pytest.fail("invalid policy reached reviewer")

    result = generate(
        context, contract, Provider(model_output(candidate(contract, **change))), review=forbidden
    )
    assert result.failure.stage == "semantic"


@pytest.mark.parametrize(
    "mode", ["reject", "wrong_text", "wrong_contract", "invalid_review", "timeout"]
)
def test_review_failure_never_retries_generation_or_exposes_candidate(context, contract, mode):
    provider = Provider(model_output(candidate(contract)))

    async def review(*args):
        if mode == "reject":
            raise c.ContractError("schema", "private review failure")
        if mode == "timeout":
            raise TimeoutError("private timeout")
        if mode == "wrong_text":
            return c.QuestionReview("다른 문장", contract)
        if mode == "wrong_contract":
            return c.QuestionReview(
                candidate(contract).text, replace(contract, purpose="다른 목적")
            )
        return None

    result = generate(context, contract, provider, review=review)
    assert not result.succeeded and result.data is None
    assert result.failure.error_code in ("director_review_failed", "director_review_timeout")
    assert "private" not in repr(result)
    assert result.attempts == (metadata(),)
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"allowed_personas": ()},
        {"allowed_personas": ("tech_lead",)},
        {"current_turn_id": "not-first"},
        {"persona_counts": (c.PersonaCount("hr_manager", 1),)},
    ],
)
def test_invalid_first_question_input_is_rejected_without_model_call(context, contract, change):
    provider = Provider(model_output(candidate(contract)))
    result = generate(replace(context, **change), contract, provider)
    assert not result.succeeded and result.failure.stage == "semantic"
    assert provider.requests == []


def test_zero_budget_is_failure_without_a_model_call(context, contract):
    provider = Provider(model_output(candidate(contract)))
    result = generate(replace(context, limits=c.ContextLimits(0, 0, "fixture")), contract, provider)
    assert result.failure.stage == "budget" and result.attempts == ()
    assert provider.requests == []


def test_one_remaining_call_limits_the_provider_request(context, contract):
    provider = Provider(model_output(candidate(contract)))
    result = generate(replace(context, limits=c.ContextLimits(1, 0, "fixture")), contract, provider)
    assert result.succeeded
    assert provider.requests[0].max_attempts == 1


@pytest.mark.parametrize(
    "mode",
    [
        "wrong_sha",
        "unknown_repo",
        "duplicate_evidence",
        "duplicate_repository",
        "duplicate_jd",
        "duplicate_history",
    ],
)
def test_untrusted_context_reference_scope_never_reaches_model(context, contract, mode):
    context = technical_context(context)
    if mode == "wrong_sha":
        context = replace(context, evidence=(replace(context.evidence[0], git_ref="b" * 40),))
    elif mode == "unknown_repo":
        context = replace(context, repositories=())
    elif mode == "duplicate_evidence":
        context = replace(context, evidence=context.evidence * 2)
    elif mode == "duplicate_repository":
        context = replace(context, repositories=context.repositories * 2)
    elif mode == "duplicate_jd":
        context = replace(context, jd_requirements=context.jd_requirements * 2)
    else:
        context = replace(context, history=context.history * 2)
    provider = Provider(model_output(candidate(contract)))
    result = generate(context, contract, provider)
    assert result.failure.stage == "semantic" and provider.requests == []


def test_posting_reference_requires_explicit_source_text(context, contract):
    ref = c.BasisRef("job_posting", "posting-1")
    contract = replace(contract, basis_refs=(ref,))
    provider = Provider(model_output(candidate(contract)))
    failed = generate(context, contract, provider)
    assert failed.failure.stage == "semantic" and provider.requests == []
    result = generate(context, contract, provider, reference_texts={ref: "팀 소개"})
    assert result.succeeded
    assert provider.requests[0].payload["reference_texts"] == [
        {"kind": "job_posting", "id": "posting-1", "text": "팀 소개"}
    ]


def test_extra_reference_cannot_replace_or_invent_context_evidence(context, contract):
    context = technical_context(context)
    for sources in (
        {c.BasisRef("evidence", "ev-1"): "tampered"},
        {c.BasisRef("evidence", "new"): "new"},
    ):
        provider = Provider(model_output(candidate(contract)))
        result = generate(context, contract, provider, reference_texts=sources)
        assert result.failure.stage == "semantic" and provider.requests == []


def test_reviewer_cancellation_propagates(context, contract):
    provider = Provider(model_output(candidate(contract)))

    async def cancelled(*args):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        generate(context, contract, provider, review=cancelled)
    assert len(provider.requests) == 1


@pytest.mark.parametrize("stage", ["timeout", "provider", "parse", "schema", "semantic", "budget"])
def test_provider_failures_preserve_metadata_and_do_not_run_reviewer(context, contract, stage):
    failure = c.CallFailure(stage, "llm_failed", "provider failure")

    async def failed(request, validator: Callable):
        return c.ModelResult(None, failure, (metadata(),))

    async def forbidden(*args):
        pytest.fail("failed generation reached reviewer")

    result = generate(context, contract, failed, review=forbidden)
    assert result.failure is failure and result.data is None
    assert result.attempts == (metadata(),)


def test_reviewer_is_actually_timed_out(context, contract):
    stopped = []

    async def blocked(*args):
        try:
            await asyncio.Future()
        finally:
            stopped.append(True)

    provider = Provider(model_output(candidate(contract)))
    result = generate(
        context, contract, provider, review=blocked, limits=c.CallLimits(0.01, 512, 65536, 65536)
    )
    assert result.failure.error_code == "director_review_timeout"
    assert stopped == [True] and len(provider.requests) == 1


def test_injected_model_cannot_bypass_prepared_contract_check(context, contract):
    async def bypass(request, validator):
        return c.ModelResult(candidate(replace(contract, purpose="unplanned")), None, (metadata(),))

    async def forbidden(*args):
        pytest.fail("unvalidated injected candidate reached reviewer")

    result = generate(context, contract, bypass, review=forbidden)
    assert result.failure.stage == "semantic" and result.data is None


def test_self_review_and_model_ids_do_not_appear_in_checked_output(context, contract):
    raw = model_output(candidate(contract))
    raw.update(passed=True, turn_id="model-id", next_step="finish")
    result = generate(context, contract, Provider(raw))
    assert result.failure.stage == "schema" and result.data is None


@pytest.mark.parametrize("max_attempts", [0, 3, True, 1.5])
def test_attempt_limit_cannot_expand_retry_policy(max_attempts):
    with pytest.raises(c.ContractError):
        c.ModelRequest(
            c.PromptSpec("director", "v1", "model", "draft"),
            {},
            "Question",
            "1",
            {},
            c.CallLimits(1, 1, 1, 1),
            max_attempts=max_attempts,
        )


@pytest.mark.parametrize(
    "sources", [[], ["not a mapping"], {c.BasisRef("job_posting", "job"): " "}]
)
def test_invalid_source_container_returns_input_failure(context, contract, sources):
    provider = Provider(model_output(candidate(contract)))
    result = generate(context, contract, provider, reference_texts=sources)
    assert result.failure.error_code == "director_input_invalid"
    assert provider.requests == []


def test_only_checked_analysis_is_forwarded_as_interpretation(context, contract):
    first = generate(context, contract, Provider(model_output(candidate(contract)))).data
    text = "캐시를 담당했습니다."
    analysis = c.AnswerAnalysis(
        "evaluated",
        "sufficient",
        (c.CoveredPoint("role", (text,)),),
        (),
        c.TechnicalAssessment("역할 설명", (), (), ("구현 품질 미평가",)),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("개인 기여 미확인",),
    )
    checked = c.validate_analysis(
        analysis,
        question=first,
        answer_text=text,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )
    context = technical_context(context)
    question = candidate(contract, persona="tech_lead")
    provider = Provider(model_output(question))
    result = generate(context, contract, provider, answer_analysis=checked)
    assert result.succeeded
    assert provider.requests[0].payload["answer_analysis"] == c.to_data(checked)
    assert provider.requests[0].payload["context"]["history"][0]["answer"] == text
    provider = Provider(model_output(question))
    rejected = generate(context, contract, provider, answer_analysis=analysis)
    assert rejected.failure.stage == "schema" and provider.requests == []
