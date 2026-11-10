"""공개 결과를 바꾸기 전에 원본 결과·점수·근거를 불변 버전으로 보존한다."""

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewReport, ReportScore
from app.db.models.report import ReportRevision


def _json(value: object) -> object:
    if isinstance(value, UUID | datetime | Decimal):
        return str(value)
    raise TypeError("Unsupported report snapshot value")


async def preserve(db: AsyncSession, report: InterviewReport) -> None:
    scores = list(
        await db.scalars(
            select(ReportScore)
            .where(ReportScore.report_id == report.id)
            .order_by(ReportScore.score_key)
        )
    )
    snapshot = {
        "headline": report.headline,
        "summary": report.summary,
        "total_score": report.total_score,
        "feedback_json": report.feedback_json,
        "coverage_json": report.coverage_json,
        "model": report.model,
        "prompt_version": report.prompt_version,
        "generated_at": report.generated_at,
        "scores": [
            {
                "score_key": row.score_key,
                "score": row.score,
                "reason": row.reason,
                "evidence_turn_ids": row.evidence_turn_ids,
            }
            for row in scores
        ],
    }
    safe = json.loads(json.dumps(snapshot, default=_json, ensure_ascii=False))
    await db.execute(
        insert(ReportRevision)
        .values(report_id=report.id, revision=report.current_revision, snapshot=safe)
        .on_conflict_do_nothing(index_elements=[ReportRevision.report_id, ReportRevision.revision])
    )
