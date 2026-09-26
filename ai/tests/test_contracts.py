from dataclasses import FrozenInstanceError

import pytest

from devon_ai import contracts as c


@pytest.fixture
def contract_data() -> dict[str, object]:
    return {
        "purpose": "캐시 선정 근거 확인",
        "required_points": [{"key": "choice", "description": "선정 이유"}],
        "assumptions": [],
        "basis_refs": [{"kind": "evidence", "id": "ev-1"}],
        "evaluation_scope": "캐시 선정 이유",
    }


def test_decode_builds_frozen_nested_contract_and_ignores_unowned_extra_fields(
    contract_data: dict[str, object],
) -> None:
    contract_data["schema_version"] = "not-owned-here"
    result = c.decode(c.QuestionContract, contract_data)

    assert result.basis_refs == (c.BasisRef("evidence", "ev-1"),)
    assert not hasattr(result, "schema_version")
    with pytest.raises(FrozenInstanceError):
        result.purpose = "changed"


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.pop("purpose"),
        lambda data: data.update(purpose=" "),
        lambda data: data.update(required_points=[]),
        lambda data: data["required_points"].append({"key": "choice", "description": "duplicate"}),
        lambda data: data.update(basis_refs=[{"kind": "unknown", "id": "ev-1"}]),
    ],
)
def test_question_contract_rejects_missing_empty_duplicate_and_unknown_values(
    contract_data: dict[str, object], change: object
) -> None:
    change(contract_data)  # type: ignore[operator]
    with pytest.raises(c.ContractError) as failure:
        c.decode(c.QuestionContract, contract_data)
    assert failure.value.stage in ("schema", "semantic")


def _question(contract_data: dict[str, object]) -> c.Question:
    return c.decode(
        c.Question,
        {
            "persona": "tech_lead",
            "text": "캐시를 선택한 이유는 무엇인가요?",
            "topic_code": "cache_choice",
            "question_contract": contract_data,
            "evidence_refs": ["ev-1"],
            "jd_requirement_ids": ["jd-1"],
            "turn_id": "ignored-model-id",
        },
    )


def _checked_question(contract_data: dict[str, object]) -> c.ContractChecked[c.Question]:
    question = _question(contract_data)
    return c.validate_question(
        question,
        review=c.QuestionReview(question.text, question.question_contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset({"ev-1"}),
        basis_refs=frozenset({c.BasisRef("evidence", "ev-1")}),
        jd_requirement_ids=frozenset({"jd-1"}),
    )


def test_question_requires_independent_review_and_registered_references(
    contract_data: dict[str, object],
) -> None:
    checked = _checked_question(contract_data)
    assert checked.data.persona == "tech_lead"
    assert not hasattr(checked.data, "turn_id")

    with pytest.raises(c.ContractError):
        c.validate_question(
            _question(contract_data),
            review=c.QuestionReview("다른 질문", _question(contract_data).question_contract),
            allowed_personas=("tech_lead",),
            evidence_refs=frozenset({"ev-1"}),
            basis_refs=frozenset({c.BasisRef("evidence", "ev-1")}),
            jd_requirement_ids=frozenset({"jd-1"}),
        )


def _analysis() -> c.AnswerAnalysis:
    return c.decode(
        c.AnswerAnalysis,
        {
            "evaluation_status": "evaluated",
            "sufficiency": "sufficient",
            "covered_points": [{"key": "choice", "answer_quotes": ["부하를 줄이려고"]}],
            "missing_points": [],
            "technical_assessment": {
                "explanation": "선정 이유를 설명함",
                "answer_quotes": ["부하를 줄이려고"],
                "evidence_refs": ["ev-1"],
                "limitations": [],
            },
            "contribution_scope": {"scope": "unknown", "answer_quotes": []},
            "claim_checks": [],
            "needs_verification": False,
            "verification_requests": [],
            "limitations": ["개인 기여 미확인"],
        },
    )


def test_answer_analysis_checks_quotes_question_scope_and_evidence(
    contract_data: dict[str, object],
) -> None:
    result = c.validate_analysis(
        _analysis(),
        question=_checked_question(contract_data),
        answer_text="부하를 줄이려고 캐시를 선택했습니다",
        evidence_refs=frozenset({"ev-1"}),
        allowed_locations=frozenset(),
    )
    assert result.data.sufficiency == "sufficient"

    with pytest.raises(c.ContractError):
        c.validate_analysis(
            _analysis(),
            question=_checked_question(contract_data),
            answer_text="다른 답변",
            evidence_refs=frozenset({"ev-1"}),
            allowed_locations=frozenset(),
        )


def test_unknown_overall_sufficiency_preserves_points_that_were_observed(
    contract_data: dict[str, object],
) -> None:
    analysis = _analysis()
    analysis = c.AnswerAnalysis(
        "needs_clarification",
        None,
        analysis.covered_points,
        (),
        analysis.technical_assessment,
        analysis.contribution_scope,
        (),
        False,
        (),
        ("수정 특성은 추가 확인 필요",),
    )
    checked = c.validate_analysis(
        analysis,
        question=_checked_question(contract_data),
        answer_text="부하를 줄이려고 캐시를 선택했습니다",
        evidence_refs=frozenset({"ev-1"}),
        allowed_locations=frozenset(),
    )
    assert checked.data.sufficiency is None
    assert checked.data.covered_points[0].key == "choice"


def test_director_decision_cannot_override_controller_permission(
    contract_data: dict[str, object],
) -> None:
    question = _checked_question(contract_data)
    decision = c.DirectorDecision(
        "ask", "선정 이유 확인", "tech_lead", "캐시 선정 근거 확인", (), "질문 목적 유지"
    )
    assert (
        c.validate_decision(
            decision,
            question=question,
            allowed_personas=("tech_lead",),
            finish_allowed=False,
            allowed_locations=frozenset(),
        ).data.next_step
        == "ask"
    )

    with pytest.raises(c.ContractError):
        c.validate_decision(
            c.DirectorDecision("finish", "종료", None, None, (), "모델이 종료 선택"),
            question=None,
            allowed_personas=(),
            finish_allowed=False,
            allowed_locations=frozenset(),
        )


def test_evidence_requires_a_real_location_and_valid_line_range() -> None:
    item = c.Evidence(
        evidence_id="ev-1",
        repository_id="repo-1",
        git_ref="a" * 40,
        source_kind="source_file",
        path="src/cache.py",
        metadata_key=None,
        content="code",
        tool_name=None,
        summary=None,
        start_line=2,
        end_line=4,
    )
    assert item.path == "src/cache.py"

    with pytest.raises(c.ContractError):
        c.Evidence("ev-2", "repo-1", "a" * 40, "source_file", None, None, "code", None, None)
    with pytest.raises(c.ContractError):
        c.Evidence(
            "ev-2",
            "repo-1",
            "a" * 40,
            "source_file",
            "src/cache.py",
            None,
            "code",
            None,
            None,
            4,
            2,
        )


def test_evidence_validates_fixed_ref_and_omitted_optional_fields() -> None:
    payload = {
        "evidence_id": None,
        "repository_id": "repo-1",
        "git_ref": "a" * 40,
        "source_kind": "source_file",
        "path": "src/cache.py",
        "metadata_key": None,
        "content": "code",
        "tool_name": None,
    }
    item = c.decode(c.Evidence, payload)
    assert item.summary is None and item.start_line is None and item.end_line is None

    without_tool = {key: value for key, value in payload.items() if key != "tool_name"}
    with pytest.raises(c.ContractError) as missing:
        c.decode(c.Evidence, without_tool)
    assert missing.value.stage == "schema" and missing.value.field == "tool_name"

    payload["git_ref"] = "main"
    with pytest.raises(c.ContractError):
        c.decode(c.Evidence, payload)


def test_git_ref_sha_errors_name_the_field_without_echoing_input() -> None:
    invalid_git_ref = "private-invalid-ref"
    factories = (
        lambda: c.Evidence(
            None,
            "repo-1",
            invalid_git_ref,
            "source_file",
            "src/cache.py",
            None,
            "code",
            None,
        ),
        lambda: c.ContextRepository("repo-1", invalid_git_ref, True, (), ()),
    )

    for factory in factories:
        with pytest.raises(c.ContractError) as failure:
            factory()
        assert failure.value.stage == "schema"
        assert failure.value.field == "git_ref"
        assert invalid_git_ref not in str(failure.value)


def test_metadata_evidence_cannot_claim_source_line_numbers() -> None:
    with pytest.raises(c.ContractError):
        c.Evidence(None, None, None, "commit", None, "commit_count", "3", None, None, 1, 1)


def test_source_path_evidence_requires_repository_and_fixed_ref() -> None:
    with pytest.raises(c.ContractError):
        c.Evidence(None, None, None, "source_file", "src/cache.py", None, "code", None)


def test_tool_result_preserves_valid_items_after_partial_tool_error() -> None:
    item = c.Evidence(
        evidence_id=None,
        repository_id="repo-1",
        git_ref="a" * 40,
        source_kind="source_file",
        path="src/cache.py",
        metadata_key=None,
        content="code",
        tool_name="github_file",
    )
    result = c.ToolResult(
        "tool_error", (item,), ("src/cache.py",), ("src/other.py 미확인",), "github_timeout"
    )
    assert result.items == (item,)

    with pytest.raises(c.ContractError):
        c.ToolResult("tool_error", (), (), (), None)


def test_tool_result_requires_actual_search_scope_or_preparation_limitation() -> None:
    with pytest.raises(c.ContractError):
        c.ToolResult("not_found", (), (), (), None)
    with pytest.raises(c.ContractError):
        c.ToolResult("insufficient_analysis", (), (), (), None)


def test_context_first_question_uses_none_and_empty_history() -> None:
    context = c.Context(
        interview_id="interview-1",
        current_turn_id=None,
        turn_no=1,
        total_turns=9,
        persona_counts=(c.PersonaCount("tech_lead", 0), c.PersonaCount("hr_manager", 0)),
        allowed_personas=("hr_manager",),
        jd_requirements=(),
        repositories=(),
        history=(),
        current_question_contract=None,
        evidence=(),
        domain_frames=(),
        limits=c.ContextLimits(2, 1, "sprint1"),
    )
    assert context.current_turn_id is None
    assert context.history == ()


def test_optional_nested_contract_keeps_semantic_error_stage(contract_data) -> None:
    contract_data["required_points"].append({"key": "choice", "description": "Duplicate"})
    payload = {
        "interview_id": "interview-1",
        "current_turn_id": "turn-1",
        "turn_no": 1,
        "total_turns": 9,
        "persona_counts": [],
        "allowed_personas": ["hr_manager"],
        "jd_requirements": [],
        "repositories": [],
        "history": [],
        "current_question_contract": contract_data,
        "evidence": [],
        "domain_frames": [],
        "limits": {"remaining_calls": 1, "remaining_replans": 1, "policy_version": "1"},
    }
    with pytest.raises(c.ContractError) as failure:
        c.decode(c.Context, payload)
    assert failure.value.stage == "semantic"


@pytest.mark.parametrize("stage", ["parse", "schema", "semantic"])
def test_candidate_failure_never_becomes_checked_success(stage: c.FailureStage) -> None:
    failure = c.CandidateFailure(stage, "후보 거절")
    assert not isinstance(failure, c.ContractChecked)
