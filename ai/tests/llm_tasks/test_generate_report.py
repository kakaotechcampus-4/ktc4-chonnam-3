import asyncio

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import report

LIMITS = c.CallLimits(1, 4096, 65536, 65536)
PROMPTS = {
    "report": c.PromptSpec("report", "report_v1", "fixture-model", "template"),
    "report_score": c.PromptSpec("report_score", "report_score_v1", "fixture-model", "template"),
}
PERSONAS = [
    "hr_manager", "tech_lead", "tech_lead", "domain_lead", "tech_lead",
    "tech_lead", "domain_lead", "tech_lead", "tech_lead",
]  # fmt: skip
KEYS = ("project_understanding", "technical_reasoning", "problem_solving",
        "communication", "contribution_clarity", "company_job_fit")  # fmt: skip
CONTRACT = {
    "purpose": "목적",
    "required_points": [{"key": "k", "description": "내용"}],
    "assumptions": [],
    "basis_refs": [],
    "evaluation_scope": "평가 범위",
}


def evidence(usage):
    return {
        "id": "e1", "usage": usage, "source_type": "file", "path": "build.gradle",
        "repository_id": "repo-1", "git_ref": "a" * 40, "metadata_key": None, "tool_name": None,
        "start_line": 1, "end_line": 2, "snippet": "implementation redis", "summary": None,
    }  # fmt: skip


def payload(**changes):
    turns = [
        {
            "turn_no": n,
            "persona": persona,
            "question": f"질문{n}",
            "answer": f"답변{n}",
            "question_contract": CONTRACT,
            "analysis": None,
            "parent_turn_no": 2 if n == 4 else None,
            "jd_requirement_ids": [],
            # 같은 근거가 질문 근거이자 평가 근거인 경우
            "evidences": [evidence("question_basis"), evidence("evaluation_basis")]
            if n == 2
            else [],
        }
        for n, persona in enumerate(PERSONAS, 1)
    ]
    rubrics = {key: {str(level): f"{key} {level}" for level in range(5)} for key in KEYS}
    return {"score_keys": list(KEYS), "rubrics": rubrics, "turns": turns, **changes}


def score_output(level=3):
    return {
        "judgments": [
            {"turn_id": str(n), "key": key, "level": level}
            for n, persona in enumerate(PERSONAS, 1)
            for key in c.SCORE_CANDIDATE_KEYS[persona]
        ]
    }


def claim(text="관찰", turns=("2",), evidence_refs=()):
    return {"text": text, "turn_refs": list(turns), "evidence_refs": list(evidence_refs)}


def narrative_output(limitations_only=False):
    def persona(name):
        item = {
            "persona": name,
            "tags": ["Redis"],
            "strengths": [claim(f"{name} 강점")],
            "improvements": [claim(f"{name} 개선", evidence_refs=("e1",))],
            "practice_actions": [claim()],
            "limitations": [],
        }
        if limitations_only:
            item = {**item, "strengths": [], "improvements": [], "practice_actions": []}
            item["limitations"] = ["근거를 조회하지 못했다"]
        return item

    empty = [] if limitations_only else [claim("요약")]
    return {
        "headline": "근거를 갖고 설명하는 지원자",
        "summary": {k: empty for k in ("strengths", "gaps", "follow_ups", "practice_actions")},
        "persona_feedbacks": [persona(p) for p in c.NARRATIVE_PERSONAS],
    }


@pytest.fixture
def run(kit):
    def _run(raw_payload=None, *, score=None, narrative=None, prompts=PROMPTS):
        providers = [
            kit.Provider(score or score_output()),
            kit.Provider(narrative or narrative_output()),
        ]
        calls = iter(providers)
        raw = asyncio.run(
            report.generate_report(
                raw_payload or payload(),
                prompts=prompts,
                limits=LIMITS,
                model_call_factory=lambda: next(calls),
            )
        )
        return raw, providers

    return _run


def test_returns_the_draft_shape_the_backend_validates(run):
    raw, (score, narrative) = run()
    assert set(raw) == {"headline", "summary", "scores", "feedbacks"}  # total_score는 없다
    assert {k: v["score"] for k, v in raw["scores"].items()} == dict.fromkeys(KEYS, 70)
    assert raw["scores"]["project_understanding"]["reason"] is None
    assert raw["scores"]["project_understanding"]["evidence_turn_nos"] == [2, 3, 5, 6, 8, 9]
    assert raw["scores"]["communication"]["evidence_turn_nos"] == list(range(1, 10))
    assert [f["persona"] for f in raw["feedbacks"]] == list(c.NARRATIVE_PERSONAS)
    assert raw["feedbacks"][0]["strengths"] == ["hr_manager 강점"]
    assert raw["summary"].startswith("강점\n- 요약\n\n부족한 점\n- 요약")
    assert len(score.requests) == len(narrative.requests) == 1


def test_image_jd_notes_and_limits_reach_score_and_narrative_without_becoming_evidence(run):
    import hashlib
    import json

    note = {
        "requirement_id": "jd-image",
        "block_id": "I0-P1-E0",
        "source_field": "job_posting.source_blocks",
        "content": "Python 개발 경험",
        "location": '{"page":1,"element":0}',
        "text_hash": hashlib.sha256("Python 개발 경험".encode()).hexdigest(),
        "image_hash": "a" * 64,
        "limitations": ["jd_image:image_count_limit"],
        "read_scope": "entire_block",
    }
    source = payload(
        requirements=[
            {
                "id": "jd-image",
                "text": "Python 개발 경험",
                "category": "required",
                "source_field": "job_posting.source_blocks",
            }
        ],
        source_notes=[note],
        limitations=["jd_image:image_count_limit"],
    )
    source["turns"][1]["jd_requirement_ids"] = ["jd-image"]
    _, providers = run(source)
    for provider in providers:
        request = provider.requests[0].payload
        assert json.loads(json.dumps(request["source_notes"])) == [note]
        assert "jd_image:image_count_limit" in request["limitations"]
        assert {item["evidence_id"] for item in request["evidence"]} == {"e1"}
    score = providers[0].requests[0].payload
    assert score["turns"][1]["jd_requirements"][0]["source_field"] == "job_posting.source_blocks"


@pytest.mark.parametrize("failure", ["unasked", "hash", "excerpt_without_limit"])
def test_invalid_jd_source_note_is_rejected_before_generating_a_report(run, failure):
    import hashlib

    note = {
        "requirement_id": "jd-image",
        "block_id": "I0-P1-E0",
        "source_field": "job_posting.source_blocks",
        "content": "Python",
        "location": "page=1",
        "text_hash": hashlib.sha256(b"Python").hexdigest(),
        "image_hash": "a" * 64,
        "limitations": [],
        "read_scope": "entire_block",
    }
    source = payload(
        requirements=[{"id": "jd-image", "text": "Python", "category": "required"}],
        source_notes=[note],
    )
    if failure != "unasked":
        source["turns"][1]["jd_requirement_ids"] = ["jd-image"]
    if failure == "hash":
        note["text_hash"] = "b" * 64
    if failure == "excerpt_without_limit":
        note["read_scope"] = "prefix_excerpt"
    with pytest.raises(c.ContractError, match="JD source|JD source excerpt|JD source content"):
        run(source)


def test_a_follow_up_and_a_doubly_used_evidence_are_carried_into_the_narrative_input(run):
    _, (_, narrative) = run()
    request = narrative.requests[0].payload
    assert request["turns"][3]["follows"] == "2"
    assert request["turns"][1]["evidence_refs"] == ["e1"]
    assert len(request["evidence"]) == 1


def test_real_partial_tool_status_and_historical_limitations_reach_the_narrative(run):
    from dataclasses import asdict

    source = c.Evidence(
        "e1",
        "repo-1",
        "a" * 40,
        "file",
        "build.gradle",
        None,
        "implementation redis",
        None,
        None,
        1,
        2,
    )
    data = payload()
    data["tool_results"] = [
        {
            "turn_id": "2",
            "result": asdict(
                c.ToolResult(
                    "insufficient_analysis",
                    (source,),
                    ("build.gradle:1-2",),
                    ("tail unread",),
                    None,
                )
            ),
        }
    ]
    data["limitations"] = ["historical_tool_status_unavailable:3"]
    import json

    _, (score, narrative) = run(json.loads(json.dumps(data)))
    assert (
        narrative.requests[0].payload["tool_results"][0]["result"]["status"]
        == "insufficient_analysis"
    )
    assert narrative.requests[0].payload["limitations"] == ["historical_tool_status_unavailable:3"]
    assert (
        score.requests[0].payload["tool_results"][0]["result"]["status"] == "insufficient_analysis"
    )


@pytest.mark.parametrize(
    "kind,notes",
    [
        ("document_claim", ("document_claim_unverified", "historical_document_claim")),
        (
            "document_visual",
            (
                "generated_visual_interpretation_not_transcription",
                "not_personal_contribution_evidence",
            ),
        ),
        ("external_source", ("external_reference_not_personal_contribution_evidence",)),
    ],
)
def test_both_report_tasks_receive_the_actual_referenced_supplemental_text_without_code_conversion(
    run,
    kind,
    notes,
):
    from dataclasses import asdict

    data = payload()
    data["turns"][1]["question_contract"] = {
        **data["turns"][1]["question_contract"],
        "basis_refs": [{"kind": kind, "id": "source-1"}],
    }
    data["supplemental_sources"] = [
        asdict(
            c.SupplementalSource(
                "source-1",
                kind,
                "Stored source passage",
                "https://example.org/guide",
                "b" * 64,
                notes,
            )
        )
    ]
    import json

    _, providers = run(json.loads(json.dumps(data)))
    for provider in providers:
        sources = provider.requests[0].payload["supplemental_sources"]
        assert sources[0]["content"] == "Stored source passage"
        assert sources[0]["kind"] == kind and sources[0]["version"] == "b" * 64
        assert sources[0]["limitations"] == notes
    assert all(
        item["evidence_id"] != "source-1" for item in providers[1].requests[0].payload["evidence"]
    )


def test_only_limitations_still_gives_a_non_empty_summary(run):
    raw, _ = run(narrative=narrative_output(limitations_only=True))
    assert raw["summary"] == "관찰 한계\n" + "\n".join(["- 근거를 조회하지 못했다"] * 3)


def test_a_failed_score_judgment_fails_the_report_even_though_the_narrative_ran(run):
    # 두 task는 동시에 호출하므로 서술도 이미 호출됐지만 리포트는 점수 실패로 끝난다.
    with pytest.raises(c.ContractError):
        run(score={"judgments": []})


def test_the_two_tasks_run_concurrently(kit):
    started, release = [], asyncio.Event()

    async def slow(request, validator):
        started.append(request.schema_name)
        if len(started) == 2:  # 둘 다 시작해야 풀린다. 순차 호출이면 영원히 기다린다.
            release.set()
        await asyncio.wait_for(release.wait(), 1)
        raw = score_output() if request.schema_name == "ScoreJudgments" else narrative_output()
        return c.ModelResult(validator(raw), None, (kit.metadata(),))

    raw = asyncio.run(
        report.generate_report(
            payload(), prompts=PROMPTS, limits=LIMITS, model_call_factory=lambda: slow
        )
    )
    assert sorted(started) == ["ReportNarrative", "ScoreJudgments"]
    assert raw["scores"]


@pytest.mark.parametrize("failed_schema", ["ScoreJudgments", "ReportNarrative"])
def test_a_concurrent_task_failure_cannot_return_a_partial_report(kit, failed_schema):
    started, completed, calls = [], [], []
    release = asyncio.Event()

    def factory():
        task_calls = []
        calls.append(task_calls)

        async def call(request, validator):
            task_calls.append(request.schema_name)
            started.append(request.schema_name)
            if len(started) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), 1)
            completed.append(request.schema_name)
            if request.schema_name == failed_schema:
                failure = c.CallFailure("timeout", "llm_timeout", "검증용 timeout")
                return c.ModelResult(None, failure, (kit.metadata(),))
            raw = score_output() if request.schema_name == "ScoreJudgments" else narrative_output()
            return c.ModelResult(validator(raw), None, (kit.metadata(),))

        return call

    # 두 task가 별도 callable을 받고 모두 끝나도 한쪽 실패를 성공 리포트로 바꾸지 않는다.
    with pytest.raises(c.ContractError) as error:
        asyncio.run(
            report.generate_report(
                payload(), prompts=PROMPTS, limits=LIMITS, model_call_factory=factory
            )
        )
    assert error.value.field == "llm_timeout"
    assert sorted(completed) == ["ReportNarrative", "ScoreJudgments"]
    assert calls == [["ScoreJudgments"], ["ReportNarrative"]]


@pytest.mark.parametrize(
    "bad",
    [
        payload(rubrics={}),
        payload(turns=[]),
        payload(turns=[{**payload()["turns"][0], "question_contract": None}]),
        payload(turns=[{**payload()["turns"][0], "turn_no": "1"}]),
        payload(rubrics={**payload()["rubrics"], "communication": {"x": "단계"}}),
    ],
    ids=["no rubric", "no turns", "no contract", "turn_no type", "rubric level"],
)
def test_bad_payload_never_reaches_the_model(run, bad):
    with pytest.raises(c.ContractError):
        run(bad)


def test_path_evidence_without_a_repository_ref_is_rejected_not_patched(run):
    turns = payload()["turns"]
    turns[1]["evidences"] = [
        {**evidence("evaluation_basis"), "git_ref": None, "repository_id": None}
    ]
    with pytest.raises(c.ContractError):
        run(payload(turns=turns))


def test_a_missing_prompt_is_rejected(run):
    with pytest.raises(c.ContractError, match="prompts"):
        run(prompts={"report": PROMPTS["report"]})


def test_an_unanswered_turn_is_sent_as_null_and_judged_not_dropped(run):
    turns = payload()["turns"]
    turns[4]["answer"] = ""  # BE는 답하지 않은 턴을 빈 문자열로 보낸다
    output = score_output()
    for judgment in output["judgments"]:
        if judgment["turn_id"] == "5":
            judgment["level"] = 0
    raw, (score, narrative) = run(payload(turns=turns), score=output)
    assert score.requests[0].payload["turns"][4]["answer"] is None
    assert narrative.requests[0].payload["turns"][4]["answer"] is None
    assert raw["scores"]["communication"]["evidence_turn_nos"] == list(range(1, 10))
    assert raw["scores"]["communication"]["score"] == 62


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_unanswered_domain_answers_cannot_become_positive_report_scores(run, level):
    turns, output = payload()["turns"], score_output()
    for index in (3, 6):
        turns[index]["answer"] = ""
    for judgment in output["judgments"]:
        if judgment["turn_id"] in ("4", "7"):
            judgment["level"] = level
    with pytest.raises(c.ContractError) as error:
        run(payload(turns=turns), score=output)
    assert error.value.stage == "semantic"


def test_unanswered_domain_answers_can_keep_zero_instead_of_an_invented_score(run):
    turns, output = payload()["turns"], score_output()
    for index in (3, 6):
        turns[index]["answer"] = ""
    for judgment in output["judgments"]:
        if judgment["turn_id"] in ("4", "7"):
            judgment["level"] = 0
    raw, _ = run(payload(turns=turns), score=output)
    assert raw["scores"]["company_job_fit"]["score"] == 0
    assert raw["scores"]["company_job_fit"]["evidence_turn_nos"] == [4, 7]


def test_an_unanswered_unobserved_domain_turn_is_excluded_from_the_score(run):
    turns, output = payload()["turns"], score_output()
    turns[3]["answer"] = ""
    for judgment in output["judgments"]:
        if judgment["turn_id"] == "4":
            judgment["level"] = "not_applicable"
    raw, _ = run(payload(turns=turns), score=output)
    assert raw["scores"]["company_job_fit"]["score"] == 70
    assert raw["scores"]["company_job_fit"]["evidence_turn_nos"] == [7]


def test_unanswered_domain_answers_all_not_applicable_still_fail_without_defaulting(run):
    turns, output = payload()["turns"], score_output()
    for index in (3, 6):
        turns[index]["answer"] = ""
    for judgment in output["judgments"]:
        if judgment["turn_id"] in ("4", "7"):
            judgment["level"] = "not_applicable"
    with pytest.raises(c.ContractError, match="unscorable key"):
        run(payload(turns=turns), score=output)


def test_the_narrative_request_carries_each_turns_question_contract(run):
    _, (_, narrative) = run()
    turn = narrative.requests[0].payload["turns"][0]
    assert turn["question_contract"]["evaluation_scope"] == "평가 범위"
    assert turn["analysis"] is None  # 분석이 없는 턴에서도 질문 당시의 평가 범위가 남는다


def test_persona_only_narrative_still_gives_a_summary(run):
    narrative = narrative_output()
    narrative["summary"] = {k: [] for k in ("strengths", "gaps", "follow_ups", "practice_actions")}
    raw, _ = run(narrative=narrative)
    assert raw["summary"].startswith("[인사 담당] 강점\n- hr_manager 강점")
    assert "[기술 리드] 부족한 점" in raw["summary"]


def test_no_unscorable_key_detail_is_lost_through_the_call_layer(run):
    # kit.Provider는 공통 호출 계층처럼 검증 실패를 일반 코드로 바꿔 돌려준다.
    judgments = [
        {**j, "level": "not_applicable"} if j["key"] == "company_job_fit" else j
        for j in score_output()["judgments"]
    ]
    with pytest.raises(c.ContractError) as error:
        run(score={"judgments": judgments})
    assert error.value.field == "unscorable key"


def test_a_bad_report_prompt_stops_everything_before_any_model_call(kit):
    called = []
    prompts = {**PROMPTS, "report": PROMPTS["report_score"]}
    with pytest.raises(c.ContractError, match="prompts"):
        asyncio.run(
            report.generate_report(
                payload(),
                prompts=prompts,
                limits=LIMITS,
                model_call_factory=lambda: called.append(1),
            )
        )
    assert called == []
