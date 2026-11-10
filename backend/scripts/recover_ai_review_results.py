"""확인된 문서 캐시·프로필 전달만 사전 상태 대조 후 복구한다. 기본은 조회다."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    InterviewReport,
    InterviewSession,
    ProfileRefreshRequest,
    User,
    UserDocument,
)
from app.features.profile.refresh_outbox import MAX_DISPATCH_ATTEMPTS, PAGE_SIZE
from scripts.configure_ai_knowledge import KnowledgeTarget, _target_identity

type Audit = Callable[[dict[str, Any]], None]


class RecoveryError(ValueError):
    """복구 대상·실행 환경·검토한 상태가 일치하지 않는다."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


async def recover_results(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    target: KnowledgeTarget,
    *,
    user_id: UUID,
    document_ids: tuple[UUID, ...] = (),
    request_ids: tuple[UUID, ...] = (),
    actor: str,
    reason: str,
    apply: bool = False,
    expected_sha256: str | None = None,
    audit: Audit | None = None,
) -> dict[str, Any]:
    if settings.app_env not in {"local", "dev"}:
        raise RecoveryError("Explicit non-production recovery required")
    if (
        not actor.strip()
        or len(actor) > 128
        or not reason.strip()
        or len(reason) > 500
        or not 1 <= len(document_ids) + len(request_ids) <= PAGE_SIZE
        or len(set(document_ids)) != len(document_ids)
        or len(set(request_ids)) != len(request_ids)
    ):
        raise RecoveryError("Explicit bounded recovery identities and reason required")
    if apply and (audit is None or expected_sha256 is None):
        raise RecoveryError("Reviewed state and durable audit required before apply")
    target_hash = _target_identity(settings.database_url, target)
    engine = sessions.kw.get("bind")
    if engine is None or _target_identity(str(engine.url), target) != target_hash:
        raise RecoveryError("Recovery session target differs")
    documents: list[UserDocument] = []
    requests: list[ProfileRefreshRequest] = []
    state: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        if await db.scalar(select(func.current_database())) != target.database:
            raise RecoveryError("Connected recovery database differs")
        user = await db.get(User, user_id, with_for_update=True)
        if user is None or user.status != "active":
            raise RecoveryError("Active recovery owner required")
        for identity in sorted(document_ids):
            document = await db.get(UserDocument, identity, with_for_update=True)
            if (
                document is None
                or document.user_id != user_id
                or document.claims_status != "succeeded"
                or document.claims_run_id is not None
                or document.claims_lease_expires_at is not None
            ):
                raise RecoveryError("Document is not an idle successful extraction")
            snapshot = document.source_snapshot or {}
            source = snapshot.get("text")
            if (
                not isinstance(source, str)
                or not source
                or not document.claims_prompt_version
                or hashlib.sha256(source.encode()).hexdigest() != snapshot.get("text_hash")
                or document.claims_source_version != snapshot.get("text_hash")
            ):
                raise RecoveryError("Preserved document source required")
            live = await db.scalar(
                select(InterviewSession.id)
                .join(AnalysisJob, InterviewSession.analysis_job_id == AnalysisJob.id)
                .where(
                    InterviewSession.user_id == user_id,
                    # 준비 실패도 첫 질문을 재사용해 재개할 수 있으므로 종료 전에는 보존한다.
                    InterviewSession.status.not_in(("completed", "abandoned")),
                    or_(
                        AnalysisJob.document_id == identity,
                        AnalysisJob.cover_letter_document_id == identity,
                    ),
                )
                .limit(1)
            )
            if live is not None:
                raise RecoveryError("Document belongs to a live interview")
            documents.append(document)
            state.append(
                {
                    "document_id": str(identity),
                    "status": document.claims_status,
                    "source_version": document.claims_source_version,
                    "prompt_version": document.claims_prompt_version,
                    "active_ids": document.claims_active_ids,
                }
            )
        for identity in sorted(request_ids):
            request = await db.get(ProfileRefreshRequest, identity, with_for_update=True)
            if (
                request is None
                or request.user_id != user_id
                or request.status != "failed"
                or request.last_error != "internal_error"
                or request.owner_token is not None
                or request.lease_expires_at is not None
                or request.expires_at <= now
                or request.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS
            ):
                raise RecoveryError("Profile delivery is not eligible for bounded recovery")
            current = await db.scalar(
                select(InterviewReport.id)
                .join(InterviewSession, InterviewReport.interview_session_id == InterviewSession.id)
                .where(
                    InterviewReport.id == request.report_id,
                    InterviewReport.current_revision == request.report_revision,
                    InterviewSession.user_id == user_id,
                    InterviewSession.status == "completed",
                )
            )
            if current is None:
                raise RecoveryError("Published owned report revision required")
            requests.append(request)
            state.append(
                {
                    "request_id": str(identity),
                    "status": request.status,
                    "report_id": str(request.report_id),
                    "revision": request.report_revision,
                    "attempts": request.dispatch_attempts,
                    "expires_at": request.expires_at.isoformat(),
                    "generated_sha256": _digest(request.generated_result),
                    "generation_may_be_required": request.generated_result is None,
                }
            )
        state_hash = _digest({"target": target_hash, "owner": str(user_id), "state": state})
        result = {
            "mode": "applied" if apply else "dry_run",
            "actor": actor,
            "reason": reason,
            "target_sha256": target_hash,
            "user_id": str(user_id),
            "state_sha256": state_hash,
            "targets": state,
        }
        if apply:
            if state_hash != expected_sha256:
                raise RecoveryError("Recovery state changed after review")
            assert audit is not None
            # 쓰기 전 감사 기록을 확정한다. 원문·생성 문장·접속 비밀은 기록하지 않는다.
            audit({**result, "mode": "applying", "at": now.isoformat()})
            for document in documents:
                document.claims_status, document.claims_error_code = "pending", None
                document.claims_active_ids = []
            for request in requests:
                request.status, request.last_error = "pending", "profile_review_recovery"
                request.next_attempt_at = now
            await db.flush()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--profile", choices=("development", "test"), required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--document-id", type=UUID, action="append", default=[])
    parser.add_argument("--profile-request-id", type=UUID, action="append", default=[])
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expected-state-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = Settings(_env_file=args.env_file)
        target = KnowledgeTarget(
            args.profile, args.target_host, args.target_port, args.target_database
        )
        if config.app_env not in {"local", "dev"}:
            raise RecoveryError("Explicit non-production recovery required")
        _target_identity(config.database_url, target)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # JSONL은 applying 기록을 fsync한 뒤에만 DB 변경을 시작한다.
        with args.output.open("x", encoding="utf-8") as output:

            def audit(event: dict[str, Any]) -> None:
                output.write(json.dumps(event, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())

            async def operate() -> dict[str, Any]:
                engine = create_async_engine(config.database_url)
                try:
                    return await recover_results(
                        async_sessionmaker(engine, expire_on_commit=False),
                        config,
                        target,
                        user_id=args.user_id,
                        document_ids=tuple(args.document_id),
                        request_ids=tuple(args.profile_request_id),
                        actor=args.actor,
                        reason=args.reason,
                        apply=args.apply,
                        expected_sha256=args.expected_state_sha256,
                        audit=audit,
                    )
                finally:
                    await engine.dispose()

            result = asyncio.run(operate())
            audit({**result, "at": datetime.now(UTC).isoformat()})
    except Exception:
        print("Recovery failed; preserve audit and inspect the explicit targets.", file=sys.stderr)
        return 1
    print(json.dumps({"mode": result["mode"], "state_sha256": result["state_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
