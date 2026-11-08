"""저장된 최초 분석·검증된 보강 분석·실제 Tool 상태의 리포트 연결을 검사한다."""

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, TurnEvidence
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


async def test_report_restores_v6_attempts_without_replacing_the_private_audit_output(
    app, db, ctx, prompt
):
    _, _, final = await _history(db, ctx)
    raw = {
        "coverage_assessment": {
            "evaluation_status": final["evaluation_status"],
            "sufficiency": final["sufficiency"],
            "covered_points": {"k": ["answer:0001"]},
            "missing_points": [],
            "limitations": final["limitations"],
        },
        "technical_assessment": {
            "explanation": final["technical_assessment"]["explanation"],
            "quote_ids": ["answer:0001"],
            "evidence_refs": final["technical_assessment"]["evidence_refs"],
            "limitations": final["technical_assessment"]["limitations"],
        },
        "contribution_scope": {
            "scope": "unknown",
            "quote_ids": [],
            "unknown_reason": "역할 확인 불가",
        },
        "claim_checks": [],
        "verification_requests": [],
        "external_queries": [],
    }
    encoded = json.dumps(raw, ensure_ascii=False)
    record = await db.scalar(select(LLMCallRecord))
    record.attempts = [
        {
            **record.attempts[0],
            "prompt_version": "answer_analysis_v6@fixture",
            "schema_version": "6",
            "raw_output": encoded,
        }
    ]
    await db.commit()
    generator = FakeGenerator()
    await service.generate_report(
        app.state.session_factory,
        interview_id=ctx[0].id,
        llm=LLM,
        http_client=None,
        generator=generator,
    )
    restored = generator.calls[0]["turns"][0]["analysis"]
    assert restored["sufficiency"] == "sufficient"
    assert restored["limitations"] == [*final["limitations"], "역할 확인 불가"]
    await db.refresh(record)
    assert record.attempts[0]["raw_output"] == encoded


async def test_ocr_and_category_conflict_limits_survive_checked_history_enrichment(
    app, db, ctx, prompt
):
    from app.db.models import JobPosting

    await _history(db, ctx)
    posting = await db.get(JobPosting, ctx[0].job_posting_id)
    posting.raw_payload = {
        "_image_extraction": {
            "limitations": ["image_source_text_limit", "image_structured_category_conflict"]
        }
    }
    await db.commit()
    generator = FakeGenerator()
    await service.generate_report(
        app.state.session_factory,
        interview_id=ctx[0].id,
        llm=LLM,
        http_client=None,
        generator=generator,
    )
    assert "jd_image:image_source_text_limit" in generator.calls[0]["limitations"]
    assert "jd_image:image_structured_category_conflict" in generator.calls[0]["limitations"]


async def test_invalid_saved_augmentation_is_rejected_before_report_inference(app, db, ctx, prompt):
    await _history(db, ctx, invalid=True)
    generator = FakeGenerator()
    with pytest.raises(ReportDraftInvalidError, match="history"):
        await service.generate_report(
            app.state.session_factory,
            interview_id=ctx[0].id,
            llm=LLM,
            http_client=None,
            generator=generator,
        )
    assert generator.calls == []


@pytest.mark.parametrize("referenced", [False, True])
async def test_legacy_source_without_location_is_excluded_but_referenced_missing_source_is_rejected(
    app, db, ctx, prompt, referenced
):
    await _history(db, ctx)
    missing = await make_evidence(db, ctx[0], ctx[1], path=None)
    if referenced:
        record = await db.scalar(select(LLMCallRecord))
        attempts = list(record.attempts)
        raw = json.loads(attempts[0]["raw_output"])
        raw["technical_assessment"]["evidence_refs"] = [str(missing.id)]
        attempts[0] = {**attempts[0], "raw_output": json.dumps(raw)}
        record.attempts = attempts
    await db.commit()
    generator = FakeGenerator()
    if referenced:
        with pytest.raises(ReportDraftInvalidError, match="history"):
            await service.generate_report(
                app.state.session_factory,
                interview_id=ctx[0].id,
                llm=LLM,
                http_client=None,
                generator=generator,
            )
        assert generator.calls == []
        return
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
    assert f"historical_source_invalid:{missing.id}" in generator.calls[0]["limitations"]


async def test_report_receives_only_referenced_supplemental_text_with_limits(app, db, ctx, prompt):
    import hashlib
    from datetime import UTC, datetime, timedelta

    from app.db.models import AnalysisJob, DocumentClaim, InterviewExternalSource, UserDocument

    turn_id, _, _ = await _history(db, ctx)
    document = UserDocument(
        user_id=ctx[0].user_id,
        filename="synthetic.pdf",
        doc_type="portfolio",
        mime_type="application/pdf",
        size_bytes=3,
        extracted_text="new",
        extracted_github_urls=[],
        extract_status="succeeded",
        is_truncated=False,
        claims_active_ids=[],
        source_snapshot={
            "text_hash": hashlib.sha256(b"new").hexdigest(),
            "source_hash": "a" * 64,
            "metadata": {
                "visual_interpretations": [
                    {
                        "page": 1,
                        "element": "diagram",
                        "description": "Generated diagram interpretation",
                    }
                ]
            },
        },
    )
    db.add(document)
    await db.flush()
    run = await db.get(AnalysisJob, ctx[0].analysis_job_id)
    run.document_id = document.id
    claim = DocumentClaim(
        document_id=document.id,
        claim_text="old unverified claim",
        source_text="Original old claim passage",
        source_version=hashlib.sha256(b"old").hexdigest(),
        source_location={"page": 1},
    )
    db.add(claim)
    external_id = uuid4()
    for source_id, content, retrieved in [
        (external_id, "Actual official passage " * 1000, datetime.now(UTC) - timedelta(days=3)),
        *((uuid4(), "unasked recent passage " * 1000, datetime.now(UTC)) for _ in range(5)),
    ]:
        db.add(
            InterviewExternalSource(
                id=source_id,
                user_id=ctx[0].user_id,
                interview_session_id=ctx[0].id,
                query_text="reference",
                url=f"https://example.org/{source_id}",
                content=content,
                content_scope="extracted_page",
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                retrieved_at=retrieved,
                limitations=[],
            )
        )
    await db.flush()
    turn = await db.get(InterviewTurn, turn_id)
    turn.question_contract = {
        **turn.question_contract,
        "basis_refs": [
            {"kind": "document_claim", "id": str(claim.id)},
            {"kind": "document_visual", "id": f"{document.id}:visual:1:diagram"},
            {"kind": "external_source", "id": str(external_id)},
        ],
    }
    await db.commit()
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
    data = generator.calls[0]
    sources = data["supplemental_sources"]
    assert {item["kind"] for item in sources} == {
        "document_claim",
        "document_visual",
        "external_source",
    }
    assert len(sources) == 3 and sum(len(item["content"].encode()) for item in sources) <= 16384
    old = next(item for item in sources if item["kind"] == "document_claim")
    assert (
        "Original old claim passage" in old["content"]
        and "historical_document_claim" in old["limitations"]
    )
    web = next(item for item in sources if item["kind"] == "external_source")
    assert web["source_id"] == str(external_id) and len(web["content"].encode()) <= 4096
    assert "context_excerpt" in web["limitations"]
    assert all(
        item["id"] not in {str(claim.id), str(external_id)}
        for item in data["turns"][0]["evidences"]
    )
