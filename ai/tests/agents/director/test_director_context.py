import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c


@pytest.fixture
def evidence():
    return c.AnalysisEvidence(
        "ev-1", "repo-1", "sha-fixed", "code", "src/cache.py", "cache.invalidate(key)", "get_file"
    )


@pytest.fixture
def locations():
    return frozenset({("repo-1", "sha-fixed", "src/cache.py")})


def test_source_content_is_required_for_registered_ids(plan, run_director):
    with pytest.raises(c.ContractError):
        run_director(
            plan=replace(plan, contract=replace(plan.contract, basis_refs=("jd-1",))),
            basis_refs=frozenset({"jd-1"}),
        )


def test_prepared_basis_and_jd_are_grounded_in_supplied_source_text(plan, question, run_director):
    plan = replace(plan, contract=replace(plan.contract, basis_refs=("jd-1",)))
    question = replace(question, question_contract=plan.contract, jd_requirement_ids=("jd-1",))
    result, calls, _ = run_director(
        question,
        plan=plan,
        basis_refs=frozenset({"jd-1"}),
        jd_requirement_ids=frozenset({"jd-1"}),
        reference_texts=(c.ReferenceText("jd-1", "변경이 잦은 데이터의 일관성 관리"),),
    )
    assert isinstance(result, c.QuestionReady)
    assert json.loads(calls[0].input_json)["reference_texts"] == [
        {"reference_id": "jd-1", "content": "변경이 잦은 데이터의 일관성 관리"}
    ]


def test_stale_evidence_is_rejected_before_generation(run_director, evidence, locations):
    with pytest.raises(c.ContractError):
        run_director(
            evidence=(replace(evidence, git_ref="old-sha"),),
            evidence_refs=frozenset({"ev-1"}),
            allowed_locations=locations,
        )


def test_tool_results_preserve_error_and_only_selected_items(
    question, run_director, evidence, locations
):
    tool = c.AnalysisToolResult(
        "tool_error", (evidence,), ("src/cache.py",), ("다른 파일 조회 실패",), "lookup_failed"
    )
    result, calls, _ = run_director(question, tool_results=(tool,), allowed_locations=locations)
    assert isinstance(result, c.QuestionReady)
    payload = json.loads(calls[0].input_json)
    assert payload["evidence"] == [] and payload["tool_results"][0]["items"] == []
    assert payload["tool_results"][0]["status"] == "tool_error"
    assert evidence.content not in calls[0].input_json
    result, calls, _ = run_director(
        replace(question, evidence_refs=("ev-1",)),
        tool_results=(tool,),
        evidence_refs=frozenset({"ev-1"}),
        allowed_locations=locations,
    )
    assert isinstance(result, c.QuestionReady)
    assert json.loads(calls[0].input_json)["evidence"][0]["git_ref"] == "sha-fixed"


def test_history_preserves_contribution_correction_and_original_analysis(question, run_director):
    old_question = c.validate_question(
        question,
        review=c.QuestionReview(question.text, question.question_contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    answer = c.SubmittedAnswer("answer", 2, "팀원이 구현했습니다")
    candidate = c.AnswerAnalysis(
        "not_evaluable",
        None,
        (),
        (),
        c.TechnicalAssessment("구현을 전제할 수 없음", (), (), ("직접 구현 아님",)),
        "teammate",
        (answer.text,),
        (),
        False,
        (),
        ("질문 전제 확인 필요",),
    )
    checked = c.validate_analysis(
        candidate,
        question=old_question,
        answer_text=answer.text,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )
    history = c.AnalysisHistory(old_question, answer, checked)
    before = asdict(history)
    result, calls, _ = run_director(question, history=(history,))
    assert isinstance(result, c.QuestionReady) and asdict(history) == before
    previous = json.loads(calls[0].input_json)["history"][0]
    assert previous["analysis"]["contribution_scope"] == "teammate"
    assert previous["answer"]["turn"] == 2
    assert previous["question"]["persona"] == "tech_lead"
