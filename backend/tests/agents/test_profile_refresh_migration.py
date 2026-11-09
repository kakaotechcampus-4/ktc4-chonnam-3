"""빈 전달 테이블은 왕복하고 실제 요청 이력은 downgrade로 삭제하지 않는다."""

from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, inspect

from app.db.base import Base
from app.db.models import InterviewReport, ProfileRefreshRequest
from app.features.profile.refresh_outbox import ensure_request


async def test_empty_roundtrip_and_populated_downgrade_guard(
    agent_sessions, agent_seed, monkeypatch
):
    migration = import_module("migrations.versions.0012_profile_refresh_outbox")
    engine = agent_sessions.kw["bind"]

    def roundtrip(connection):
        context = MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
        monkeypatch.setattr(migration, "op", Operations(context))
        migration.downgrade()
        migration.upgrade()
        # 현재 ORM을 검증할 때 후속의 임시 생성 결과 컬럼도 같은 스키마에 복원한다.
        generated = import_module("migrations.versions.0017_profile_generation_result")
        monkeypatch.setattr(generated, "op", Operations(context))
        generated.upgrade()
        inspector = inspect(connection)
        assert {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("profile_refresh_requests")
        } == {("report_id", "report_revision")}
        assert {
            item["name"] for item in inspector.get_check_constraints("profile_refresh_requests")
        } == {
            item.name
            for item in Base.metadata.tables["profile_refresh_requests"].constraints
            if isinstance(item, CheckConstraint)
        }

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

    def guarded(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="audit must be preserved"):
            migration.downgrade()

    async with engine.begin() as connection:
        await connection.run_sync(guarded)
    async with agent_sessions() as db:
        assert (await db.get(ProfileRefreshRequest, rid)).status == "pending"
