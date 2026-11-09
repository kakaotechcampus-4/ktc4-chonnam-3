"""재실행 메타데이터는 왕복하고 보존해야 할 실행 중 결과는 downgrade로 버리지 않는다."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.models import InterviewReport, ProfileRefreshRequest
from app.features.profile.refresh_outbox import ensure_request


async def test_profile_generated_result_round_trip_and_pending_result_guard(
    agent_sessions, agent_seed, monkeypatch
):
    migration = import_module("migrations.versions.0017_profile_generation_result")
    engine = agent_sessions.kw["bind"]

    def roundtrip(connection):
        monkeypatch.setattr(
            migration,
            "op",
            Operations(
                MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
            ),
        )
        migration.downgrade()
        assert "generated_result" not in {
            item["name"] for item in inspect(connection).get_columns("profile_refresh_requests")
        }
        migration.upgrade()
        column = next(
            item
            for item in inspect(connection).get_columns("profile_refresh_requests")
            if item["name"] == "generated_result"
        )
        assert column["nullable"] is True and str(column["type"]) == "JSONB"

    async with engine.begin() as connection:
        await connection.run_sync(roundtrip)
    async with agent_sessions.begin() as db:
        report = InterviewReport(
            interview_session_id=agent_seed["interview_id"],
            headline="총평",
            summary="원본",
            total_score=60,
        )
        db.add(report)
        await db.flush()
        rid = await ensure_request(
            db, user_id=agent_seed["owner"], report_id=report.id, report_revision=1
        )
        row = await db.get(ProfileRefreshRequest, rid)
        row.generated_result = {"fingerprint": "a" * 64, "role_summary": "보존할 성공 요약"}

    def guarded(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="pending profile generation"):
            migration.downgrade()

    async with engine.begin() as connection:
        await connection.run_sync(guarded)
    async with agent_sessions() as db:
        assert (await db.get(ProfileRefreshRequest, rid)).generated_result[
            "role_summary"
        ] == "보존할 성공 요약"


async def test_document_claim_lease_round_trip_and_active_reservation_guard(
    agent_sessions, agent_seed, monkeypatch
):
    migration = import_module("migrations.versions.0018_document_claim_lease")
    engine = agent_sessions.kw["bind"]

    def roundtrip(connection):
        monkeypatch.setattr(
            migration,
            "op",
            Operations(
                MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
            ),
        )
        migration.downgrade()
        assert "claims_lease_expires_at" not in {
            item["name"] for item in inspect(connection).get_columns("user_documents")
        }
        migration.upgrade()
        column = next(
            item
            for item in inspect(connection).get_columns("user_documents")
            if item["name"] == "claims_lease_expires_at"
        )
        assert column["nullable"] is True and column["type"].timezone is True

    async with engine.begin() as connection:
        await connection.run_sync(roundtrip)
    identity, expires = uuid4(), datetime.now(UTC) + timedelta(minutes=1)
    async with agent_sessions.begin() as db:
        await db.execute(
            text(
                "INSERT INTO user_documents(id,user_id,filename,mime_type,size_bytes,"
                "extract_status,claims_status,claims_lease_expires_at) "
                "VALUES (:id,:owner,'source.md','text/plain',"
                "10,'succeeded','running',:expires)"
            ),
            {"id": identity, "owner": agent_seed["owner"], "expires": expires},
        )

    def guarded(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="active document claim"):
            migration.downgrade()

    async with engine.begin() as connection:
        await connection.run_sync(guarded)
    async with agent_sessions() as db:
        assert (
            await db.scalar(
                text("SELECT claims_lease_expires_at FROM user_documents WHERE id=:id"),
                {"id": identity},
            )
            == expires
        )
