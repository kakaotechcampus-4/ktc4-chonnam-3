import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c


def checked_question(purpose, key, text):
    contract = c.QuestionContract(purpose, (c.RequiredPoint(key, purpose),), (), (), purpose)
    raw = c.Question("tech_lead", text, "followup", contract, (), ())
    return c.validate_question(
        raw,
        review=c.QuestionReview(text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )


def test_followup_preserves_original_turn_and_analysis_for_later_feedback(
    question,
    answer,
    analysis,
    run_analysis,
):
    original, _ = run_analysis(analysis)
    history = c.AnalysisHistory(question, answer, original.data)
    before = asdict(history)
    followup = checked_question("수정 특성 확인", "writes", "수정 특성은 어떤가요?")
    analysis.update(
        sufficiency="sufficient",
        missing_points=[],
        covered_points=[{"key": "writes", "answer_quotes": ["수정은 드뭅니다"]}],
    )
    analysis["technical_assessment"].update(answer_quotes=["수정은 드뭅니다"])
    result, calls = run_analysis(
        analysis,
        question=followup,
        question_turn=3,
        answer=c.SubmittedAnswer("answer", 3, "수정은 드뭅니다"),
        history=(history,),
    )
    assert isinstance(result, c.ModelSuccess) and result.data.data.sufficiency == "sufficient"
    assert asdict(history) == before
    previous = json.loads(calls[0].input_json)["history"][0]
    assert previous["answer"]["turn"] == 2 and previous["answer"]["text"] == answer.text
    assert previous["analysis"]["sufficiency"] == "partial"
    assert previous["analysis"]["missing_points"] == ["writes"]
    assert "persona" not in previous["question"]


def test_teammate_correction_is_preserved_without_rewriting_prior_claim(
    question,
    answer,
    analysis,
    run_analysis,
):
    analysis.update(contribution_scope="self", contribution_quotes=["캐시했습니다"])
    original, _ = run_analysis(analysis)
    history = c.AnalysisHistory(question, answer, original.data)
    role = checked_question("본인 담당 범위 확인", "role", "본인이 담당한 범위는 무엇인가요?")
    analysis.update(
        sufficiency="sufficient",
        missing_points=[],
        contribution_scope="teammate",
        contribution_quotes=["팀원이 구현했습니다"],
        covered_points=[{"key": "role", "answer_quotes": ["팀원이 구현했습니다"]}],
    )
    analysis["technical_assessment"].update(
        explanation="담당 범위 정정이며 기술 주장 없음",
        answer_quotes=[],
        limitations=["기술 정확성 평가 범위 밖"],
    )
    result, calls = run_analysis(
        analysis,
        question=role,
        question_turn=3,
        answer=c.SubmittedAnswer("answer", 3, "팀원이 구현했습니다"),
        history=(history,),
    )
    assert result.data.data.contribution_scope == "teammate"
    assert history.analysis.data.contribution_scope == "self"
    payload = json.loads(calls[0].input_json)
    assert payload["history"][0]["analysis"]["contribution_scope"] == "self"
    assert payload["answer"]["text"] == "팀원이 구현했습니다"


def test_history_cannot_lend_its_quotes_to_the_current_answer(
    question,
    answer,
    analysis,
    run_analysis,
):
    original, _ = run_analysis(analysis)
    history = c.AnalysisHistory(question, answer, original.data)
    result, _ = run_analysis(
        analysis,
        question_turn=3,
        answer=c.SubmittedAnswer("answer", 3, "모르겠습니다"),
        history=(history,),
    )
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "semantic"


def test_future_or_duplicate_history_is_rejected_before_call(
    question, answer, analysis, run_analysis
):
    original, _ = run_analysis(analysis)
    history = c.AnalysisHistory(question, answer, original.data)
    with pytest.raises(c.ContractError):
        run_analysis(history=(history,))
    with pytest.raises(c.ContractError):
        run_analysis(question_turn=3, answer=replace(answer, turn=3), history=(history, history))


def test_history_analysis_must_match_its_original_answer(question, answer, analysis, run_analysis):
    original, _ = run_analysis(analysis)
    with pytest.raises(c.ContractError):
        c.AnalysisHistory(question, replace(answer, text="다른 답변"), original.data)
