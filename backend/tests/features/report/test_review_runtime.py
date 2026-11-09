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


async def test_failed_reassessment_keeps_the_successful_public_report_and_approval(
    app, db, ctx, prompt, redis, enqueue
):
    interview, _ = ctx
    report = await make_report(db, interview)
    row = ReportDisagreement(report_id=report.id, persona="tech_lead", reason_type="other")
    db.add(row)
    await db.commit()
    await reviews.decide(
        db,
        disagreement_id=row.id,
        expected_revision=1,
        reviewer="operator-fixture",
        reason="근거 확인",
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
    await generation.claim(app.state.session_factory, interview.id, request.id)
    with pytest.raises(RuntimeError):
        await service.generate_report(
            app.state.session_factory,
            interview_id=interview.id,
            llm=LLM,
            http_client=None,
            generator=FakeGenerator(error=RuntimeError("fixture")),
            generation_request_id=request.id,
        )
    await db.refresh(report)
    await db.refresh(row)
    await db.refresh(request)
    assert report.current_revision == 1 and report.headline == "헤드라인"
    assert row.status == "approved" and row.applied_revision is None
    assert request.status == "failed"


async def test_operator_cli_records_approval_then_queues_a_separate_reassessment(
    app_settings, db, ctx
):
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
        reason="근거와 평가 범위 확인",
        decision="approve_reassessment",
        apply=True,
    )
    result = await operate(app_settings, args)
    assert result["status"] == "approved"
    assert await db.scalar(select(func.count()).select_from(ReportGenerationRequest)) == 0
    args.action = "reassess"
    result = await operate(app_settings, args)
    assert result["mode"] == "queued"
    request = (await db.scalars(select(ReportGenerationRequest))).one()
    assert request.mode == "reassessment" and request.status == "queued"
    assert request.requested_by == "operator-fixture"
    await db.refresh(report)
    assert report.current_revision == 1


async def test_prompt_change_during_generation_discards_old_results(
    app, db, ctx, prompt, redis, enqueue
):
    from sqlalchemy import update

    from app.db.models import PromptVersion

    interview, _ = ctx
    request = await generation.enqueue(
        db, redis, interview_id=interview.id, user_id=interview.user_id
    )
    await generation.claim(app.state.session_factory, interview.id, request.id)

    class ChangingGenerator(FakeGenerator):
        async def __call__(self, *args, **kwargs):
            value = await super().__call__(*args, **kwargs)
            async with app.state.session_factory.begin() as other:
                await other.execute(
                    update(PromptVersion)
                    .where(PromptVersion.task_name == "report")
                    .values(is_active=False)
                )
                other.add(
                    PromptVersion(
                        task_name="report",
                        version="next-fixture",
                        model="report-model",
                        template="새 검토 기준",
                        is_active=True,
                    )
                )
            return value

    result = await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=ChangingGenerator(),
        generation_request_id=request.id,
    )
    assert result == "skipped"
    await db.refresh(request)
    assert request.status == "stale" and request.error_code == "report_input_changed"
    assert await db.scalar(select(func.count()).select_from(InterviewReport)) == 0


async def test_cancelled_queue_delivery_does_not_leave_an_active_orphan(db, ctx, redis, enqueue):
    interview, _ = ctx
    enqueue.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await generation.enqueue(db, redis, interview_id=interview.id, user_id=interview.user_id)
    request = (await db.scalars(select(ReportGenerationRequest))).one()
    assert request.status == "enqueue_failed"
    assert await redis.exists(f"report:gen:{interview.id}") == 0


async def test_report_records_the_actual_provider_model_instead_of_the_configured_alias(
    app, db, ctx, prompt, monkeypatch
):
    from devon_ai import contracts as c

    async def model_call(request, validator, **kwargs):
        metadata = c.AttemptMetadata(
            1,
            "fixture",
            "actual-provider-model",
            request.prompt.version,
            request.schema_version,
            1,
            1,
            1,
        )
        return c.ModelResult({}, None, (metadata,))

    monkeypatch.setattr(service, "call_model", model_call)

    class ObservedGenerator(FakeGenerator):
        async def __call__(self, payload, *, prompts, limits, model_call_factory):
            request = c.ModelRequest(
                prompts["report"], {}, "fixture", "1", {"type": "object"}, limits
            )
            await model_call_factory()(request, lambda value: value)
            return await super().__call__(
                payload, prompts=prompts, limits=limits, model_call_factory=model_call_factory
            )

    interview, _ = ctx
    await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=ObservedGenerator(),
    )
    report = (await db.scalars(select(InterviewReport))).one()
    assert report.model == "actual-provider-model"


async def test_report_tasks_use_and_audit_their_own_time_limits(
    app, db, ctx, prompt, redis, enqueue, monkeypatch
):
    from devon_ai import contracts as c

    observed = {}

    async def model_call(request, validator, **kwargs):
        observed[request.prompt.task_name] = request.limits.timeout_seconds
        metadata = c.AttemptMetadata(
            1,
            "fixture",
            request.prompt.model,
            request.prompt.version,
            request.schema_version,
            1,
            1,
            1,
        )
        return c.ModelResult({}, None, (metadata,))

    monkeypatch.setattr(service, "call_model", model_call)

    class Generator(FakeGenerator):
        async def __call__(self, payload, *, prompts, limits, model_call_factory):
            for name in ("report", "report_score"):
                request = c.ModelRequest(
                    prompts[name], {}, "fixture", "1", {"type": "object"}, limits
                )
                await model_call_factory()(request, lambda value: value)
            return self.output

    interview, _ = ctx
    request = await generation.enqueue(
        db, redis, interview_id=interview.id, user_id=interview.user_id
    )
    await generation.claim(app.state.session_factory, interview.id, request.id)
    llm = LLM.model_copy(update={"llm_task_timeouts": {"report": 17, "report_score": 19}})
    await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=llm,
        http_client=None,
        generator=Generator(),
        generation_request_id=request.id,
    )
    await db.refresh(request)
    assert observed == {"report": 17, "report_score": 19}
    assert request.input_snapshot["task_limits"]["report"]["timeout_seconds"] == 17
    assert request.input_snapshot["task_limits"]["report_score"]["timeout_seconds"] == 19
