"""서버 운영자의 명시 검토·재평가 큐 요청. 기본 실행은 읽기 전용 미리보기다."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import InterviewReport, InterviewSession, ReportDisagreement
from app.db.models.report import ReportGenerationRequest, ReportRevision
from app.features.report import generation, reviews


async def operate(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            if args.action == "pending":
                rows = list(
                    await db.scalars(
                        select(ReportDisagreement)
                        .where(ReportDisagreement.status == "pending")
                        .order_by(ReportDisagreement.created_at, ReportDisagreement.id)
                        .limit(100)
                    )
                )
                return {
                    "mode": "read_only",
                    "pending": [
                        {
                            "id": str(row.id),
                            "report_id": str(row.report_id),
                            "persona": row.persona,
                            "revision": row.source_revision,
                            "reason_type": row.reason_type,
                        }
                        for row in rows
                    ],
                }
            if args.action == "inspect":
                if args.disagreement_id is None:
                    raise ValueError("Explicit disagreement identity is required")
                row = await db.get(ReportDisagreement, args.disagreement_id)
                if row is None:
                    raise ValueError("Unknown disagreement")
                report = await db.get(InterviewReport, row.report_id)
                assert report is not None
                revision = await db.scalar(
                    select(ReportRevision).where(
                        ReportRevision.report_id == row.report_id,
                        ReportRevision.revision == row.source_revision,
                    )
                )
                request = await db.scalar(
                    select(ReportGenerationRequest)
                    .where(
                        ReportGenerationRequest.interview_session_id == report.interview_session_id,
                        ReportGenerationRequest.status == "succeeded",
                        ReportGenerationRequest.expected_revision == row.source_revision - 1,
                    )
                    .order_by(ReportGenerationRequest.created_at.desc())
                    .limit(1)
                )
                return {
                    "mode": "read_only",
                    "disagreement_id": str(row.id),
                    "revision": row.source_revision,
                    "reason_type": row.reason_type,
                    "comment": row.detail,
                    "status": row.status,
                    "snapshot": revision.snapshot if revision else None,
                    "input_snapshot": request.input_snapshot if request else None,
                    "limitations": []
                    if revision and request
                    else ["legacy_review_source_incomplete"],
                }
            if (
                args.disagreement_id is None
                or args.expected_revision is None
                or not args.reviewer
                or not args.reviewer.strip()
                or len(args.reviewer) > 120
            ):
                raise ValueError("Explicit review identity and revision are required")
            row = await db.get(ReportDisagreement, args.disagreement_id)
            if row is None:
                raise ValueError("Unknown disagreement")
            report = await db.get(InterviewReport, row.report_id)
            if (
                report is None
                or report.current_revision != args.expected_revision
                or row.source_revision != args.expected_revision
            ):
                raise ValueError("Report revision changed")
            if args.action == "review" and (not args.reason or args.decision is None):
                raise ValueError("Explicit decision and reason are required")
            if args.action == "reassess" and row.status != "approved":
                raise ValueError("A recorded approval is required")
            if not args.apply:
                return {
                    "mode": "dry_run",
                    "action": args.action,
                    "disagreement_id": str(row.id),
                    "revision": row.source_revision,
                }
            if args.action == "review":
                reviewed = await reviews.decide(
                    db,
                    disagreement_id=row.id,
                    expected_revision=args.expected_revision,
                    reviewer=args.reviewer,
                    reason=args.reason,
                    approve=args.decision == "approve_reassessment",
                )
                await db.commit()
                return {
                    "mode": "applied",
                    "status": reviewed.status,
                    "disagreement_id": str(row.id),
                }
            interview = await db.get(InterviewSession, report.interview_session_id)
            assert interview is not None
            redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            try:
                request = await generation.enqueue(
                    db,
                    redis,
                    interview_id=interview.id,
                    user_id=interview.user_id,
                    mode="reassessment",
                    disagreement=row,
                    actor=args.reviewer,
                )
                return {
                    "mode": "queued",
                    "request_id": str(request.id) if request else None,
                    "disagreement_id": str(row.id),
                }
            finally:
                await redis.aclose()
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pending", "inspect", "review", "reassess"))
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--disagreement-id", type=UUID)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--reviewer")
    parser.add_argument("--reason")
    parser.add_argument("--decision", choices=("retain", "approve_reassessment"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(operate(Settings(_env_file=args.env_file), args))
    except Exception:
        # 설정·접속주소·이의 본문·공급자 원문을 오류 출력에 포함하지 않는다.
        print(json.dumps({"ok": False, "error": "report_review_operation_failed"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
