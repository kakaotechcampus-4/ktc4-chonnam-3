"""명시 재시도·버전별 이의 접수·검토 후 재평가의 실행 경계."""

import asyncio
from argparse import Namespace

import pytest
from redis.exceptions import RedisError
from sqlalchemy import func, select

from app.db.models import InterviewReport, ReportDisagreement, ReportScore
from app.db.models.report import ReportGenerationRequest, ReportRevision
from app.features.report import generation, reviews, service
from app.features.report.schemas import FeedbackDisagreementRequest

from .factories import make_report
from .fakes import LLM, FakeGenerator


async def test_disagreement_is_owned_revision_scoped_and_does_not_change_scores(client, db, ctx):
    interview, _ = ctx
    report = await make_report(db, interview)
    await db.commit()
    response = await client.post(
        f"/api/interviews/{interview.id}/feedback-disagreements",
        json={
            "persona": "tech_lead",
            "reasonType": "insufficient_basis",
            "comment": "근거를 확인해주세요.",
            "expectedRevision": 1,
        },
    )
    assert response.status_code == 204
    row = (await db.scalars(select(ReportDisagreement))).one()
    assert row.source_revision == 1 and row.status == "pending" and row.reviewed_at is None
    assert await db.scalar(select(func.count()).select_from(ReportScore)) == 6
    await db.refresh(report)
    assert report.current_revision == 1
    duplicate = await client.post(
        f"/api/interviews/{interview.id}/feedback-disagreements",
        json={
            "persona": "tech_lead",
            "reasonType": "other",
            "expectedRevision": 1,
        },
    )
    assert duplicate.status_code == 409


async def test_stale_disagreement_cannot_attach_to_a_newer_result(client, db, ctx):
    interview, _ = ctx
    await make_report(db, interview, current_revision=2)
    await db.commit()
    for expected in (1, None):
        body = {"persona": "tech_lead", "reasonType": "other"}
        if expected is not None:
            body["expectedRevision"] = expected
        response = await client.post(
            f"/api/interviews/{interview.id}/feedback-disagreements", json=body
        )
        assert response.status_code == 409
    assert await db.scalar(select(func.count()).select_from(ReportDisagreement)) == 0


async def test_explicit_retry_requires_a_failure_and_no_successful_report(
    client, db, ctx, redis, enqueue
):
    interview, _ = ctx
    url = f"/api/interviews/{interview.id}/report/retry"
    assert (await client.post(url)).status_code == 409
    await redis.set(f"report:fail:{interview.id}", "llm_failed")
    assert (await client.post(url)).status_code == 202
    request = (await db.scalars(select(ReportGenerationRequest))).one()
    assert request.mode == "retry" and request.status == "queued"
    assert request.expected_revision == 0
    assert (await client.post(url)).status_code == 202
    assert enqueue.await_count == 1


async def test_initial_generation_also_preserves_a_revision(app, db, ctx, prompt):
    interview, _ = ctx
    assert (
        await service.generate_report(
            app.state.session_factory,
            interview_id=interview.id,
            llm=LLM,
            http_client=None,
            generator=FakeGenerator(),
        )
        == "created"
    )
    revision = (await db.scalars(select(ReportRevision))).one()
    assert revision.revision == 1 and len(revision.snapshot["scores"]) == 6
    assert revision.snapshot["headline"] == "한 줄 총평"


async def test_only_reviewed_explicit_reassessment_replaces_current_projection_and_keeps_old(
    app, db, ctx, prompt, redis, enqueue
):
    interview, _ = ctx
    report = await make_report(db, interview)
    await db.commit()
    await reviews.submit(
        db,
        user_id=interview.user_id,
        interview_id=interview.id,
        body=FeedbackDisagreementRequest(
            persona="tech_lead", reason_type="other", expected_revision=1
        ),
    )
    row = (await db.scalars(select(ReportDisagreement))).one()
    assert row.status == "pending"
    await reviews.decide(
        db,
        disagreement_id=row.id,
        expected_revision=1,
        reviewer="operator-fixture",
        reason="원문과 평가 범위 대조 완료",
        approve=True,
    )
    await db.commit()
    request = await generation.enqueue(
        db,
        redis,
        interview_id=interview.id,
        user_id=interview.user_id,
        mode="reassessment",
        disagreement=row,
    )
    assert request is not None
    assert await generation.claim(app.state.session_factory, interview.id, request.id) == request.id
    generator = FakeGenerator()
    generator.output["headline"] = "검토 후 새 결과"
    outcome = await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=generator,
        generation_request_id=request.id,
    )
    assert outcome == "revised" and len(generator.calls) == 1
    await db.refresh(report)
    assert report.current_revision == 2 and report.headline == "검토 후 새 결과"
    revisions = list(await db.scalars(select(ReportRevision).order_by(ReportRevision.revision)))
    assert [r.revision for r in revisions] == [1, 2]
    assert revisions[0].snapshot["headline"] == "헤드라인"
    assert revisions[1].snapshot["headline"] == "검토 후 새 결과"
    assert await db.scalar(select(func.count()).select_from(ReportScore)) == 6
    await db.refresh(row)
    assert row.status == "applied" and row.applied_revision == 2


async def test_reassessment_is_not_admitted_before_review(app, db, ctx, redis):
    from app.core.errors import AppError

    interview, _ = ctx
    report = await make_report(db, interview)
    row = ReportDisagreement(report_id=report.id, persona="tech_lead", reason_type="other")
    db.add(row)
    await db.commit()
    with pytest.raises(AppError):
        await generation.enqueue(
            db,
            redis,
            interview_id=interview.id,
            user_id=interview.user_id,
            mode="reassessment",
            disagreement=row,
        )


async def test_concurrent_explicit_retry_has_one_durable_request(client, db, ctx, redis, enqueue):
    interview, _ = ctx
    await redis.set(f"report:fail:{interview.id}", "llm_failed")
    responses = await asyncio.gather(
        *[client.post(f"/api/interviews/{interview.id}/report/retry") for _ in range(2)]
    )
    assert [r.status_code for r in responses] == [202, 202]
    assert enqueue.await_count == 1
    assert await db.scalar(select(func.count()).select_from(ReportGenerationRequest)) == 1


async def test_retry_enqueue_failure_keeps_the_original_failure_and_allows_explicit_retry(
    client, db, ctx, redis, enqueue
):
    interview, _ = ctx
    await redis.set(f"report:fail:{interview.id}", "llm_failed")
    enqueue.side_effect = RedisError("private-provider-value-must-not-be-returned")
    response = await client.post(f"/api/interviews/{interview.id}/report/retry")
    assert response.status_code == 500 and "private-provider" not in response.text
    assert await redis.get(f"report:fail:{interview.id}") == b"llm_failed"
    assert (await db.scalars(select(ReportGenerationRequest))).one().status == "enqueue_failed"
    enqueue.side_effect = None
    assert (await client.post(f"/api/interviews/{interview.id}/report/retry")).status_code == 202
    assert enqueue.await_count == 2


async def test_database_owner_blocks_duplicate_generation_after_redis_ttl_loss(
    client, db, ctx, redis, enqueue
):
    interview, _ = ctx
    assert (await client.get(f"/api/interviews/{interview.id}/report")).status_code == 202
    await redis.delete(f"report:gen:{interview.id}")
    assert (await client.get(f"/api/interviews/{interview.id}/report")).status_code == 202
    assert enqueue.await_count == 1


async def test_review_cli_preview_does_not_write_a_decision(app_settings, client, db, ctx):
    from scripts.review_report import operate

    interview, _ = ctx
    report = await make_report(db, interview)
    row = ReportDisagreement(report_id=report.id, persona="tech_lead", reason_type="other")
    db.add(row)
    await db.commit()
    args = Namespace(
        action="review",
        disagreement_id=row.id,
        expected_revision=1,
        reviewer="operator-fixture",
        reason="확인",
        decision="approve_reassessment",
        apply=False,
    )
    result = await operate(app_settings, args)
    assert result["mode"] == "dry_run"
    await db.refresh(row)
    assert row.status == "pending" and row.reviewed_at is None


async def test_expired_request_requires_explicit_retry_and_keeps_the_old_request_stale(
    client, db, ctx, redis, enqueue
):
    from datetime import UTC, datetime, timedelta

    interview, _ = ctx
    path = f"/api/interviews/{interview.id}/report"
    assert (await client.get(path)).status_code == 202
    old = (await db.scalars(select(ReportGenerationRequest))).one()
    old.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()
    assert (await client.get(path)).status_code == 409
    await db.refresh(old)
    assert old.status == "stale"
    assert (await client.post(path + "/retry")).status_code == 202
    assert enqueue.await_count == 2
