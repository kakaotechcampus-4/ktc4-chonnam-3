import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c


def shallow_input(**changes):
    return replace(
        c.ShallowRepoInput("repo", "a" * 40, "project", "readme", False, (), None, None, ()),
        **changes,
    )


def shallow_result(**changes):
    return replace(
        c.ShallowRepoAnalysis(
            "repo",
            "a" * 40,
            "purpose",
            (),
            (),
            (),
            "project role",
            (c.ShallowBasis("description", "project"),),
            ("limited",),
        ),
        **changes,
    )


def contract(**changes):
    return replace(
        c.QuestionContract("purpose", (c.RequiredPoint("point", "description"),), (), (), "scope"),
        **changes,
    )


def test_two_segments_of_one_path_keep_their_exact_source_scope():
    first = c.SourceDocument("module/service.py", "file", "one\ntwo", "lines 1-2", 1, 2)
    second = c.SourceDocument("module/service.py", "file", "two\nthree", "lines 2-3", 2, 3)
    shallow = shallow_result(basis=(c.ShallowBasis("description", "project"),))
    source = c.DeepRepoInput("repo", "a" * 40, shallow, (first, second))
    candidate = c.DeepRepoAnalysis(
        "repo",
        "a" * 40,
        "Both observed segments",
        (),
        (
            c.NotableArea(first.path, "first observation", first.read_scope, ()),
            c.NotableArea(second.path, "second observation", second.read_scope, ()),
        ),
        (),
    )
    checked = c.validate_deep_analysis(candidate, source=source)
    assert checked.data.notable_areas == candidate.notable_areas
    parsed = c.parse_deep_analysis(json.loads(json.dumps(asdict(candidate))), source=source)
    assert parsed.data.analysis == candidate


def test_segment_line_range_must_match_actual_content():
    with pytest.raises(c.ContractError, match="source line range"):
        c.SourceDocument("service.py", "file", "one\ntwo", "lines 7-9", 7, 9)


def test_same_file_and_scope_cannot_be_registered_twice():
    source = c.SourceDocument("service.py", "file", "one", "lines 7-7", 7, 7)
    shallow = shallow_result(basis=(c.ShallowBasis("description", "project"),))
    with pytest.raises(c.ContractError, match="source scopes"):
        c.DeepRepoInput("repo", "a" * 40, shallow, (source, source))


def test_shallow_structure_and_supporting_file_are_only_valid_when_provided():
    observed = c.SourceDocument(
        "module/custom.toml", "file", "dependency = 'example'", "entire file"
    )
    source = shallow_input(structure=(observed.path,), supporting_files=(observed,))
    candidate = shallow_result(
        basis=(
            c.ShallowBasis("structure", "module path"),
            c.ShallowBasis("supporting_file", "dependency", observed.path),
        )
    )
    assert c.validate_shallow_batch((source,), (candidate,)).data.succeeded == (candidate,)
    rejected = c.validate_shallow_batch((shallow_input(),), (candidate,)).data
    assert rejected.failed[0].reason_summary == "analysis basis unavailable"


def test_shallow_source_limitations_are_preserved_as_required_analysis_limitations():
    source = shallow_input(source_limitations=("source read budget exhausted",))
    candidate = shallow_result(basis=(c.ShallowBasis("description", "project"),), limitations=())
    checked = c.validate_shallow_batch((source,), (candidate,)).data
    assert checked.failed[0].reason_summary == "collection limitations missing"


def test_old_question_contract_has_no_invented_evaluation_keys():
    old = json.loads(json.dumps(asdict(contract())))
    old.pop("evaluation_keys", None)
    decoded = c.decode(c.QuestionContract, old)
    assert decoded.evaluation_keys == ()


def test_declared_evaluation_keys_allow_technical_turn_to_observe_job_fit():
    turn = c.ScoreTurn(
        "turn-1",
        "tech_lead",
        "JD와 프로젝트 경험을 연결해 설명해 주세요.",
        "answer",
        contract(evaluation_keys=("company_job_fit",)),
        ("jd-1",),
        (c.LinkedRequirement("jd-1", "required", "requirement"),),
    )
    assert c.score_candidate_keys(turn) == ("company_job_fit",)


def test_legacy_score_turn_keeps_persona_candidates_without_changing_saved_scope():
    turn = c.ScoreTurn("turn-1", "hr_manager", "question", "answer", contract())
    assert c.score_candidate_keys(turn) == c.SCORE_CANDIDATE_KEYS["hr_manager"]


def test_question_relation_rejects_follow_up_without_a_real_parent_reference():
    with pytest.raises(c.ContractError, match="question relation"):
        c.Question("tech_lead", "question", "topic", contract(), (), (), "follow_up", None)


def test_supplemental_source_preserves_document_or_web_identity_without_a_fake_git_ref():
    source = c.SupplementalSource(
        "source-1",
        "external_source",
        "official passage",
        "https://example.org/guide",
        "b" * 64,
        (),
        "Official guide",
        "2026-11-07T00:00:00Z",
    )
    assert source.version == "b" * 64
    assert not hasattr(source, "git_ref")


def test_external_query_rejects_oversized_query_before_a_provider_call():
    with pytest.raises(c.ContractError, match="external query length"):
        c.ExternalQueryRequest("x" * 1001, "clarify an external concept")


def test_report_score_receives_explicit_keys_and_their_actual_jd_reference_text():
    from devon_ai.llm_tasks.report_score import _payload

    requirement = c.LinkedRequirement("jd-1", "required", "Distributed services")
    turn = c.ScoreTurn(
        "turn-1",
        "tech_lead",
        "question",
        "answer",
        contract(evaluation_keys=("company_job_fit",)),
        ("jd-1",),
        (requirement,),
    )
    item = _payload((turn,), ())["turns"][0]
    assert item["candidate_keys"] == ["company_job_fit"]
    assert item["jd_requirement_ids"] == ["jd-1"]
    assert item["jd_requirements"][0]["text"] == "Distributed services"


def test_external_only_verification_is_a_checked_request_not_a_repository_read():
    question = c.Question("tech_lead", "question", "topic", contract(), (), ())
    checked_question = c.validate_question(
        question,
        review=c.QuestionReview(question.text, question.question_contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    analysis = c.AnswerAnalysis(
        "evaluated",
        "insufficient",
        (),
        ("point",),
        c.TechnicalAssessment("not verified", (), (), ("source missing",)),
        c.ContributionScope("unknown", ()),
        (),
        True,
        (),
        ("source missing",),
        (c.ExternalQueryRequest("official API semantics", "check the referenced concept"),),
    )
    checked = c.validate_analysis(
        analysis,
        question=checked_question,
        answer_text="모르겠습니다",
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )
    assert checked.data.verification_requests == ()
    assert checked.data.external_queries == analysis.external_queries


def test_external_search_status_does_not_disguise_failure_as_no_evidence():
    status = c.ExternalSearchStatus(
        "tool_error", (), ("official API semantics",), ("provider unavailable",), "timeout"
    )
    assert status.status == "tool_error" and status.error_code == "timeout"


def test_partial_lookup_keeps_verified_items_without_claiming_the_tail_was_read():
    item = c.Evidence("ev-1", "repo-1", "a" * 40, "file", "main.py", None, "head", "read")
    result = c.ToolResult(
        "insufficient_analysis", (item,), ("main.py:1-1",), ("tail unread",), None
    )
    assert result.items == (item,)
    assert result.status == "insufficient_analysis"
    with pytest.raises(c.ContractError):
        c.ToolResult("not_found", (item,), ("main.py",), (), None)
    with pytest.raises(c.ContractError, match="searched_scope"):
        c.ToolResult("insufficient_analysis", (item,), (), ("tail unread",), None)


def test_report_rejects_a_tool_item_that_is_not_the_registered_immutable_source():
    source = c.Evidence("ev-1", "repo-1", "a" * 40, "file", "main.py", None, "actual", "read")
    changed = replace(source, content="different")
    turn = c.ReportTurn("1", "tech_lead", "question", "answer", None, None, ("ev-1",), contract())
    tool = c.ReportToolResult("1", c.ToolResult("found", (changed,), ("main.py",), (), None))
    with pytest.raises(c.ContractError, match="tool result evidence"):
        c.validate_report_input(c.ReportInput((turn,), (source,), (tool,)))


def test_streaming_is_optional_and_does_not_accept_an_integer_as_a_boolean():
    assert c.CallLimits(1, 1024, 2048, 4096).stream is False
    assert c.CallLimits(1, 1024, 2048, 4096, stream=True).stream is True
    with pytest.raises(c.ContractError, match="stream"):
        c.CallLimits(1, 1024, 2048, 4096, stream=1)


def test_report_missing_supplemental_text_requires_an_explicit_budget_limitation():
    asked = replace(contract(), basis_refs=(c.BasisRef("external_source", "web-1"),))
    turn = c.ReportTurn("1", "tech_lead", "question", "answer", None, None, (), asked)
    with pytest.raises(c.ContractError, match="missing supplemental source"):
        c.validate_report_input(c.ReportInput((turn,), (), ()))
    bounded = c.ReportInput(
        (turn,), (), (), ("supplemental_source_outside_model_budget:external_source:web-1",)
    )
    assert c.validate_report_input(bounded) is bounded


def test_report_rejects_supplemental_material_that_no_original_question_referenced():
    source = c.SupplementalSource(
        "web-1", "external_source", "actual text", "https://example.org", "a" * 64, ()
    )
    turn = c.ReportTurn("1", "tech_lead", "question", "answer", None, None, (), contract())
    with pytest.raises(c.ContractError, match="unasked supplemental source"):
        c.validate_report_input(c.ReportInput((turn,), (), (), (), (source,)))
