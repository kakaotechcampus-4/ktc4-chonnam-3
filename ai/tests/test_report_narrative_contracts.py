from dataclasses import replace

import pytest

from devon_ai import contracts as c

REF = "a" * 40


def evidence(evidence_id="m1"):
    return c.Evidence(
        evidence_id, "repo-1", REF, "code", "build.gradle", None, "implementation redis", None
    )


CONTRACT = c.QuestionContract("목적", (c.RequiredPoint("k", "내용"),), (), (), "평가 범위")


def turn(n, persona, follows=None, evidence=(), answer=None):
    answer = f"답변{n}" if answer is None else answer
    return c.ReportTurn(f"turn-{n}", persona, f"질문{n}", answer, follows, None, evidence, CONTRACT)


def report_input(**changes):
    base = c.ReportInput(
        (turn(1, "hr_manager"), turn(2, "tech_lead", evidence=("m1",)), turn(3, "domain_lead")),
        (evidence(),),
        (),
    )
    return replace(base, **changes)


def claim(text="관찰", turns=("turn-2",), evidences=()):
    return c.NarrativeClaim(text, turns, evidences)


def persona(name, **changes):
    base = c.PersonaNarrative(name, ("Redis",), (claim(),), (claim(),), (claim(),), ())
    return replace(base, **changes)


def narrative(**changes):
    summary = c.SummaryNarrative((claim(),), (claim(),), (claim(),), (claim(),))
    base = c.ReportNarrative(
        "근거를 갖고 설명하는 지원자",
        summary,
        tuple(persona(p) for p in c.NARRATIVE_PERSONAS),
    )
    return replace(base, **changes)


def check(candidate, source=None):
    return c.validate_narrative(candidate, report_input=source or report_input())


def test_valid_narrative_passes_and_has_no_score_field():
    data = c.to_data(check(narrative()))
    assert set(data) == {"headline", "summary", "persona_feedbacks"}
    assert "score" not in str(data)


def test_a_claim_can_cite_registered_evidence():
    ok = narrative(persona_feedbacks=tuple(persona(p) for p in c.NARRATIVE_PERSONAS))
    cited = persona("tech_lead", strengths=(claim(turns=("turn-2",), evidences=("m1",)),))
    check(replace(ok, persona_feedbacks=(persona("hr_manager"), cited, persona("domain_lead"))))


def bad(**changes):
    return narrative(**changes)


@pytest.mark.parametrize(
    "candidate",
    [
        bad(headline="한 줄\n두 줄"),
        bad(headline="가" * (c.HEADLINE_MAX_CHARS + 1)),
        bad(persona_feedbacks=tuple(persona(p) for p in c.NARRATIVE_PERSONAS[:2])),
        bad(persona_feedbacks=tuple(persona("tech_lead") for _ in range(3))),
        bad(
            persona_feedbacks=(
                *(persona(p) for p in c.NARRATIVE_PERSONAS[:2]),
                persona("tech_lead"),
            )
        ),
        bad(
            persona_feedbacks=(
                persona("hr_manager", tags=()),
                persona("tech_lead"),
                persona("domain_lead"),
            )
        ),
        bad(
            persona_feedbacks=(
                persona("hr_manager", tags=("a", "b", "c", "d")),
                persona("tech_lead"),
                persona("domain_lead"),
            )
        ),
        bad(
            persona_feedbacks=(
                persona("hr_manager", tags=("가" * (c.TAG_MAX_CHARS + 1),)),
                persona("tech_lead"),
                persona("domain_lead"),
            )
        ),
        bad(
            persona_feedbacks=(
                persona("hr_manager", tags=("a", "a")),
                persona("tech_lead"),
                persona("domain_lead"),
            )
        ),
    ],
    ids=[
        "multiline headline",
        "long headline",
        "two personas",
        "same persona",
        "duplicate persona",
        "no tags",
        "four tags",
        "long tag",
        "duplicate tags",
    ],
)
def test_form_violations_are_semantic_failures(candidate):
    with pytest.raises(c.ContractError) as error:
        check(candidate)
    assert error.value.stage == "semantic"


def claim_in_summary(**kwargs):
    summary = c.SummaryNarrative((claim(**kwargs),), (), (), ())
    return narrative(summary=summary)


@pytest.mark.parametrize(
    "candidate",
    [
        claim_in_summary(turns=("turn-9",)),
        claim_in_summary(turns=("turn-2",), evidences=("m9",)),
        claim_in_summary(turns=(), evidences=()),
        claim_in_summary(turns=("turn-2", "turn-2")),
    ],
    ids=["unknown turn", "unknown evidence", "no basis at all", "duplicate ref"],
)
def test_every_claim_needs_real_references(candidate):
    with pytest.raises(c.ContractError) as error:
        check(candidate)
    assert error.value.stage == "semantic"


def test_a_claim_that_cites_only_evidence_is_allowed():
    check(claim_in_summary(turns=(), evidences=("m1",)))


@pytest.mark.parametrize(
    "source",
    [
        report_input(turns=()),
        report_input(turns=(turn(1, "hr_manager"), turn(1, "tech_lead"))),
        report_input(turns=(turn(1, "hr_manager", follows="turn-2"), turn(2, "tech_lead"))),
        report_input(turns=(turn(1, "hr_manager", follows="turn-1"),)),
        report_input(
            tool_results=(
                c.ReportToolResult(
                    "turn-9", c.ToolResult("insufficient_analysis", (), (), ("한계",), None)
                ),
            )
        ),
        report_input(evidence=(evidence("m1"), evidence("m1"))),
    ],
    ids=[
        "no turns",
        "duplicate turn",
        "follows later turn",
        "follows itself",
        "tool result turn",
        "duplicate evidence",
    ],
)
def test_bad_report_input_is_rejected(source):
    with pytest.raises(c.ContractError) as error:
        c.validate_report_input(source)
    assert error.value.stage == "semantic"


def test_follow_up_and_tool_result_inputs_are_accepted():
    tool_error = c.ToolResult("tool_error", (), (), ("조회 실패",), "tool_failed")
    source = report_input(
        turns=(turn(1, "hr_manager"), turn(2, "tech_lead", follows="turn-1")),
        tool_results=(c.ReportToolResult("turn-2", tool_error),),
    )
    assert c.validate_report_input(source) is source


def test_decode_reads_a_model_output_and_drops_nothing_required():
    raw = c.to_data(check(narrative()))
    assert c.decode(c.ReportNarrative, raw) == narrative()
    del raw["summary"]
    with pytest.raises(c.ContractError):
        c.decode(c.ReportNarrative, raw)


def test_evidence_must_belong_to_a_cited_turn():
    # m1은 turn-2에만 묶여 있다. turn-3을 인용하며 m1을 쓰면 근거가 다른 턴의 것이다.
    with pytest.raises(c.ContractError, match="evidence_refs"):
        check(claim_in_summary(turns=("turn-3",), evidences=("m1",)))
    # 여러 턴을 인용하면 그중 한 턴에 묶인 근거면 된다.
    check(claim_in_summary(turns=("turn-3", "turn-2"), evidences=("m1",)))


def test_an_evidence_only_claim_needs_evidence_linked_to_some_turn():
    source = report_input(evidence=(evidence("m1"), evidence("m2")))  # m2는 어느 턴에도 없다
    check(claim_in_summary(turns=(), evidences=("m1",)), source)
    with pytest.raises(c.ContractError, match="evidence_refs"):
        check(claim_in_summary(turns=(), evidences=("m2",)), source)


def test_a_turn_cannot_link_unregistered_evidence():
    source = report_input(turns=(turn(1, "hr_manager", evidence=("m9",)),))
    with pytest.raises(c.ContractError, match="evidence_refs"):
        c.validate_report_input(source)
