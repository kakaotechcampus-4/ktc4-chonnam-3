"""사용자 접수와 운영자 검토·명시 재평가를 분리한다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import InterviewReport, ReportDisagreement
from app.features.report import generation
from app.features.report.schemas import FeedbackDisagreementRequest
from app.shared.enums import Reason


async def submit(
    db: AsyncSession, *, user_id: UUID, interview_id: UUID, body: FeedbackDisagreementRequest
) -> None:
    await generation.locked_interview(db, interview_id, user_id)
    report = await db.scalar(
        select(InterviewReport)
        .where(InterviewReport.interview_session_id == interview_id)
        .with_for_update()
    )
    if report is None:
        raise AppError(Reason.REPORT_UNAVAILABLE)
    expected = body.expected_revision
    if expected is None and report.current_revision == 1:
        expected = 1
    if expected != report.current_revision:
        raise AppError(Reason.REPORT_UNAVAILABLE)
    created = await db.scalar(
        insert(ReportDisagreement)
        .values(
            report_id=report.id,
            source_revision=expected,
            persona=body.persona.value,
            reason_type=body.reason_type.value,
            detail=body.comment,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ReportDisagreement.report_id,
                ReportDisagreement.source_revision,
                ReportDisagreement.persona,
            ]
        )
        .returning(ReportDisagreement.id)
    )
    if created is None:
        raise AppError(Reason.ALREADY_SUBMITTED)
    await db.commit()


async def decide(
    db: AsyncSession,
    *,
    disagreement_id: UUID,
    expected_revision: int,
    reviewer: str,
    reason: str,
    approve: bool,
) -> ReportDisagreement:
    if not reviewer.strip() or not reason.strip() or len(reviewer) > 120 or len(reason) > 5000:
        raise ValueError("Reviewer identity and bounded decision reason are required")
    source = await db.get(ReportDisagreement, disagreement_id)
    if source is None:
        raise AppError(Reason.NOT_FOUND)
    report = await db.get(InterviewReport, source.report_id)
    assert report is not None
    await generation.locked_interview(db, report.interview_session_id)
    report = await db.get(
        InterviewReport, source.report_id, with_for_update=True, populate_existing=True
    )
    row = await db.get(
        ReportDisagreement, disagreement_id, with_for_update=True, populate_existing=True
    )
    assert row is not None and report is not None
    if row.source_revision != expected_revision or report.current_revision != expected_revision:
        raise AppError(Reason.REPORT_UNAVAILABLE)
    status = "approved" if approve else "retained"
    if row.status != "pending":
        if (
            row.status == status
            and row.reviewed_by == reviewer.strip()
            and row.review_reason == reason.strip()
        ):
            return row
        raise AppError(Reason.REPORT_UNAVAILABLE)
    row.status, row.reviewed_by, row.review_reason = status, reviewer.strip(), reason.strip()
    row.reviewed_at = datetime.now(UTC)
    await db.flush()
    return row
