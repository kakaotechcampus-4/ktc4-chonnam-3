"""저장된 최초 분석·검증된 보강 분석·실제 Tool 상태의 리포트 연결을 검사한다."""

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import (
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    SessionRepository,
    TurnEvidence,
)
from app.features.report import service
from app.llm_tasks.report import ReportDraftInvalidError

from ..interview.factories import make_evidence
from .fakes import LLM, FakeGenerator


async def _history(db, ctx, *, invalid=False):
    interview, repo = ctx
    turn = await db.scalar(select(InterviewTurn))
    turn.question_contract = {
        "purpose": "설명 확인",
        "required_points": [{"key": "k", "description": "설명"}],
        "assumptions": [],
        "basis_refs": [],
        "evaluation_scope": "설명",
    }
    initial = c.AnswerAnalysis(
        "evaluated",
        "insufficient",
        (),
        ("k",),
        c.TechnicalAssessment("미확인", (), (), ("원문 미확인",)),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("원문 미확인",),
    )
    turn.analysis = json.loads(json.dumps(asdict(initial)))
    evidence = await make_evidence(db, interview, repo)
    db.add(TurnEvidence(turn_id=turn.id, evidence_id=evidence.id, usage="evaluation_basis"))
    source = c.Evidence(
        str(evidence.id),
        str(repo.id),
        evidence.git_ref,
        evidence.source_type,
        evidence.path,
        None,
        evidence.snippet,
        None,
    )
    final = c.AnswerAnalysis(
        "evaluated",
        "sufficient",
        (c.CoveredPoint("k", (turn.answer_text,)),),
        (),
        c.TechnicalAssessment(
            "실제 읽은 원문 범위 확인", (turn.answer_text,), (str(evidence.id),), ("tail unread",)
        ),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("tail unread",),
    )
    raw = json.loads(json.dumps(asdict(final)))
    if invalid:
        raw["covered_points"][0]["key"] = "not-asked"
    db.add(
        LLMCallRecord(
            id=uuid4(),
            interview_session_id=interview.id,
            turn_id=turn.id,
            turn_no=turn.turn_no,
            task_name="answer_analysis",
            attempts=[
                asdict(
                    c.AttemptMetadata(
                        2,
                        "fixture",
                        "m",
                        "answer_analysis_v2",
                        "2",
                        1,
                        3,
                        4,
                        raw_output=json.dumps(raw, ensure_ascii=False),
                    )
                )
            ],
        )
    )
    result = c.ToolResult(
        "insufficient_analysis", (source,), ("src/app.py:1-1",), ("tail unread",), None
    )
    session = await db.get(InterviewSession, interview.id)
    session.context_state = {"evidence_tool_results": {str(turn.id): asdict(result)}}
    await db.commit()
    return turn.id, json.loads(json.dumps(asdict(initial))), json.loads(json.dumps(asdict(final)))


@pytest.mark.parametrize("damaged", [False, True])
async def test_absent_legacy_candidates_and_damaged_candidates_are_distinguished(
    app, db, ctx, prompt, damaged
):
    await _history(db, ctx)
    if damaged:
        ctx[0].context_state = {**ctx[0].context_state, "repository_lookup_candidates": []}
        await db.commit()
    generator = FakeGenerator()
    await service.generate_report(
        app.state.session_factory,
        interview_id=ctx[0].id,
        llm=LLM,
        http_client=None,
        generator=generator,
    )
    notes = generator.calls[0]["limitations"]
    assert ("historical_repository_candidates_invalid" in notes) is damaged


@pytest.mark.parametrize(
    "snapshot_case",
    ["matching", "different_sha", "malformed", "unselected", "missing_pin", "other_owner"],
)
async def test_report_replays_unread_lookup_candidates_only_from_owned_pinned_selection(
    app, db, ctx, prompt, snapshot_case
):
    from ..interview.factories import make_repo, make_run, make_user

    turn_id, initial, _ = await _history(db, ctx)
    interview, repo = ctx
    selected = await db.scalar(select(SessionRepository))
    selected.snapshot_head_sha = "a" * 40
    request_repo_id = str(repo.id)
    snapshot_repo_id = request_repo_id
    snapshot = {"head_sha": "a" * 40, "paths": ["src/unread.py"], "limitations": []}
    if snapshot_case == "different_sha":
        snapshot["head_sha"] = "b" * 40
    elif snapshot_case == "malformed":
        snapshot["paths"] = ["src/unread.py", "../outside.py"]
    elif snapshot_case == "unselected":
        request_repo_id = snapshot_repo_id = str(uuid4())
    elif snapshot_case == "missing_pin":
        selected.snapshot_head_sha = None
    elif snapshot_case == "other_owner":
        other_user = await make_user(db)
        other_run = await make_run(db, other_user)
        other_repo = await make_repo(db, other_run)
        db.add(
            SessionRepository(
                interview_session_id=interview.id,
                repository_id=other_repo.id,
                is_primary=False,
                display_order=1,
                snapshot_head_sha="a" * 40,
            )
        )
        request_repo_id = snapshot_repo_id = str(other_repo.id)
    turn = await db.get(InterviewTurn, turn_id)
    request = {
        "claim_text": turn.answer_text,
        "purpose": "아직 읽지 않은 주변 구현 확인",
        "repository_id": request_repo_id,
        "git_ref": "a" * 40,
        "allowed_paths": ["src/unread.py"],
    }
    record = await db.scalar(select(LLMCallRecord))
    raw = json.loads(record.attempts[0]["raw_output"])
    raw.update(needs_verification=True, verification_requests=[request])
    record.attempts = [{**record.attempts[0], "raw_output": json.dumps(raw)}]
    interview.context_state = {
        **interview.context_state,
        "repository_lookup_candidates": {snapshot_repo_id: snapshot},
    }
    original_attempts = json.loads(json.dumps(record.attempts))
    await db.commit()
    generator = FakeGenerator()
    if snapshot_case != "matching":
        with pytest.raises(ReportDraftInvalidError, match="history"):
            await service.generate_report(
                app.state.session_factory,
                interview_id=interview.id,
                llm=LLM,
                http_client=None,
                generator=generator,
            )
        assert generator.calls == []
    else:
        assert (
            await service.generate_report(
                app.state.session_factory,
                interview_id=interview.id,
                llm=LLM,
                http_client=None,
                generator=generator,
            )
            == "created"
        )
        payload = generator.calls[0]
        assert payload["turns"][0]["analysis"]["verification_requests"] == [request]
        # 조회 후보는 권한 범위일 뿐, 읽은 원문이나 Tool 성공 결과로 승격하지 않는다.
        assert all(item["path"] != "src/unread.py" for item in payload["turns"][0]["evidences"])
        assert all(
            item["path"] != "src/unread.py"
            for result in payload["tool_results"]
            for item in result["result"]["items"]
        )
    await db.refresh(turn)
    await db.refresh(record)
    assert turn.analysis == initial
    assert record.attempts == original_attempts


async def test_report_receives_final_checked_analysis_and_partial_tool_result(app, db, ctx, prompt):
    turn_id, initial, final = await _history(db, ctx)
    generator = FakeGenerator()
    assert (
        await service.generate_report(
            app.state.session_factory,
            interview_id=ctx[0].id,
            llm=LLM,
            http_client=None,
            generator=generator,
        )
        == "created"
    )
    payload = generator.calls[0]
    assert payload["turns"][0]["analysis"] == final
    assert payload["tool_results"][0]["turn_id"] == "1"
    assert payload["tool_results"][0]["result"]["status"] == "insufficient_analysis"
    assert payload["tool_results"][0]["result"]["limitations"] == ["tail unread"]
    await db.refresh(await db.get(InterviewTurn, turn_id))
    assert (await db.get(InterviewTurn, turn_id)).analysis == initial
