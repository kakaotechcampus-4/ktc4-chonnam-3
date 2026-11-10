"""합성 Wanted transport의 동일 이미지 JD가 실제 9턴과 리포트까지 이어지는지 검증한다.

외부 응답은 전부 대역이다. 실제 채용사이트 지원·모델 품질·음성 입력을 검증하지 않는다.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db.models import (
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    JdRequirement,
    JobPosting,
    SessionRepository,
)
from app.db.models.report import ReportGenerationRequest
from app.features.analysis.posting_service import get_or_fetch_posting
from tests.features.interview.factories import make_user

from .image_jd_lineage_provider import LIMIT, UNUSED, URL, USED
from .image_jd_lineage_scenario import finish_interview, generate_report, initialize, settings


async def test_fresh_create_keeps_repository_snapshot_before_checkpoint_refresh(
    app, client, monkeypatch
):
    from uuid import uuid4

    from app.features.interview import prepare

    scenario = await initialize(app, client, monkeypatch, prepare_session=False)
    sessions, iid = app.state.session_factory, scenario["interview"]
    try:
        assert sessions.kw["autoflush"] is False
        async with sessions() as db:
            selected = await db.scalar(
                select(SessionRepository).where(SessionRepository.interview_session_id == iid)
            )
            assert (selected.snapshot_head_sha, selected.is_primary) == (None, False)
            repository_id = selected.repository_id
        job_id = uuid4()
        assert await prepare._claim(sessions, scenario["owner"], iid, job_id) is False
        _, _, expected = await prepare._snapshot(sessions, scenario["owner"], iid, job_id)
        assert expected[0][:3] == (repository_id, "a" * 40, True)
        async with sessions() as db:
            selected = await db.scalar(
                select(SessionRepository).where(SessionRepository.interview_session_id == iid)
            )
            assert (
                selected.repository_id,
                selected.snapshot_head_sha,
                selected.is_primary,
            ) == (repository_id, "a" * 40, True)
    finally:
        await scenario["http"].aclose()


@pytest.mark.parametrize("condition", ["normal", "missing", "tampered", "excerpt"])
async def test_image_source_reaches_actual_interview_and_report(
    app, client, monkeypatch, condition
):
    scenario = await initialize(app, client, monkeypatch, excerpt=condition == "excerpt")
    provider, iid = scenario["provider"], scenario["interview"]
    used, unused = scenario["requirements"]
    try:
        assert (used.text, unused.text) == (USED, UNUSED)
        blocks = scenario["posting"].raw_payload["source_blocks"]
        assert (
            used.source_refs[0]["text_hash"]
            == hashlib.sha256(blocks[0]["text"].encode()).hexdigest()
        )
        assert used.source_refs[0]["image_hash"] == blocks[0]["image_hash"]
        before_cache = (len(provider.requests), provider.vision_calls, provider.posting_calls)
        cached = await get_or_fetch_posting(
            app.state.session_factory, URL, client=scenario["http"], settings=settings()
        )
        assert cached.id == scenario["posting"].id
        assert before_cache == (
            len(provider.requests),
            provider.vision_calls,
            provider.posting_calls,
        )
        await finish_interview(app, scenario)
        plans = [p for p in provider.requests if p.get("operation") == "plan"]
        assert len(plans) == 9
        second = plans[1]
        assert any(
            r["id"] == str(used.id) and r["category"] == "preferred"
            for r in second["context"]["jd_requirements"]
        )
        assert "jd_image:" + LIMIT in second["context"]["supplemental_limitations"]
        original = json.loads(
            next(r["text"] for r in second["reference_texts"] if r["kind"] == "job_posting")
        )
        assert original["source_blocks"] == blocks
        async with app.state.session_factory() as db:
            turns = list(
                await db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.interview_session_id == iid)
                    .order_by(InterviewTurn.turn_no)
                )
            )
            assert len(turns) == 9 and all(t.status == "answered" and t.analysis for t in turns)
            assert str(used.id) in [r["id"] for r in turns[1].question_contract["basis_refs"]]
            assert all(unused.id not in t.jd_requirement_ids for t in turns)
        if condition in {"missing", "tampered"}:
            async with app.state.session_factory.begin() as db:
                posting = await db.get(JobPosting, scenario["posting"].id)
                raw = copy.deepcopy(posting.raw_payload)
                if condition == "missing":
                    raw["source_blocks"] = raw["source_blocks"][1:]
                else:
                    raw["source_blocks"][0]["text"] = "해시와 일치하지 않는 전사"
                posting.raw_payload = raw
        report = await generate_report(app, client, scenario)
        assert len(report["turns"]) == 9 and report["revision"] == 1
        assert report["coverage"]["coveredRequirements"] == 1
        assert report["coverage"]["uncoveredRequirements"] == [UNUSED]
        async with app.state.session_factory() as db:
            request = await db.scalar(
                select(ReportGenerationRequest).where(
                    ReportGenerationRequest.interview_session_id == iid
                )
            )
            assert request.status == "succeeded"
            payload = request.input_snapshot["payload"]
            stored = await db.scalar(
                select(InterviewReport).where(InterviewReport.interview_session_id == iid)
            )
            assert stored.summary == report["summary"]
        narrative = next(p for p in provider.requests if "turns" in p and "rubric" not in p)
        scores = [p for p in provider.requests if "rubric" in p]
        assert scores
        assert narrative["source_notes"] == payload["source_notes"]
        assert all(str(unused.id) != note["requirement_id"] for note in payload["source_notes"])
        assert all(
            note["requirement_id"] != item.get("evidence_id")
            for note in payload["source_notes"]
            for item in narrative["evidence"]
        )
        assert narrative["evidence"]
        assert all(item["git_ref"] == "a" * 40 for item in narrative["evidence"])
        if condition in {"missing", "tampered"}:
            assert payload["source_notes"] == []
            assert any(
                item.startswith(f"jd_source_unavailable:{used.id}:")
                for item in payload["limitations"]
            )
        else:
            (note,) = payload["source_notes"]
            assert (
                note["requirement_id"] == str(used.id)
                and note["source_field"] == "job_posting.source_blocks"
            )
            assert note["image_hash"] == blocks[0]["image_hash"]
            assert note["block_id"] == used.source_refs[0]["block_id"]
            assert note["text_hash"] == used.source_refs[0]["text_hash"]
            assert note["read_scope"] == (
                "prefix_excerpt" if condition == "excerpt" else "entire_block"
            )
            assert ("coordinate" in json.loads(note["location"])) is (condition == "normal")
        assert any(
            str(used.id) in turn["jd_requirement_ids"]
            for score in scores
            for turn in score["turns"]
        )
        for score in scores:
            for turn in score["turns"]:
                assert all(
                    note["requirement_id"] in turn["jd_requirement_ids"]
                    for note in turn["source_notes"]
                )
                if str(used.id) in turn["jd_requirement_ids"]:
                    assert turn["source_notes"] == payload["source_notes"]
                else:
                    assert turn["source_notes"] == []
            assert "jd_image:" + LIMIT in score["limitations"]
        assert "jd_image:" + LIMIT in narrative["limitations"]
        assert (await client.get(f"/api/interviews/{iid}/report")).json() == report
        if condition == "normal":
            await verify_new_source_and_owner_isolation(app, client, scenario, report)
    finally:
        await scenario["http"].aclose()


async def verify_new_source_and_owner_isolation(app, client, scenario, report):
    original_payload = copy.deepcopy(scenario["posting"].raw_payload)
    original_refs = {row.id: copy.deepcopy(row.source_refs) for row in scenario["requirements"]}
    scenario["provider"].revision = 2
    new = await get_or_fetch_posting(
        app.state.session_factory,
        URL,
        client=scenario["http"],
        settings=settings(),
        now=datetime.now(UTC) + timedelta(days=8),
    )
    assert new.id != scenario["posting"].id
    async with app.state.session_factory.begin() as db:
        interview = await db.get(InterviewSession, scenario["interview"])
        assert interview.job_posting_id == scenario["posting"].id
        original = await db.get(JobPosting, scenario["posting"].id)
        assert original.raw_payload == original_payload
        previous = list(
            await db.scalars(
                select(JdRequirement).where(JdRequirement.job_posting_id == original.id)
            )
        )
        assert {row.id: row.source_refs for row in previous} == original_refs
        other = await make_user(db)
    # 기존 응답의 domain 쿠키와 중복되지 않는 별도 사용자 클라이언트로 검사한다.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:5173"
    ) as foreign:
        foreign.cookies.set("devon_session", await app.state.sessions.create(other.id))
        denied = await foreign.get(f"/api/interviews/{scenario['interview']}/report")
        assert denied.status_code == 404
    assert (await client.get(f"/api/interviews/{scenario['interview']}/report")).json() == report
