"""명시한 리뷰 복구 대상만 변경하고 원문·기존 결과·회차를 보존한다."""

import hashlib
import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    DocumentClaim,
    InterviewReport,
    InterviewSession,
    ProfileRefreshRequest,
    UserDocument,
)
from scripts.configure_ai_knowledge import KnowledgeTarget
from tests.agents.conftest import agent_seed as agent_seed
from tests.agents.conftest import agent_sessions as agent_sessions


def module():
    name = "scripts.recover_ai_review_results"
    assert importlib.util.find_spec(name) is not None, "scoped recovery command is missing"
    return importlib.import_module(name)


@pytest.fixture
async def recovery_data(agent_sessions, agent_seed):
    source = "원문은 복구 작업에서 바꾸지 않는다."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.status = "completed"
        document = UserDocument(
            user_id=agent_seed["owner"],
            filename="fixture.txt",
            mime_type="text/plain",
            size_bytes=len(source.encode()),
            extract_status="succeeded",
            claims_status="succeeded",
            source_snapshot={"text": source, "text_hash": source_hash, "blocks": []},
            claims_source_version=source_hash,
            claims_prompt_version="doc_claims_v2",
        )
        db.add(document)
        await db.flush()
        claim = DocumentClaim(
            document_id=document.id,
            claim_text=source,
            claim_type="role",
            source_version=source_hash,
            tech_tags=["OldTag"],
        )
        report = InterviewReport(
            interview_session_id=interview.id, headline="보존", summary="원본", total_score=60
        )
        db.add_all([claim, report])
        await db.flush()
        document.claims_active_ids = [str(claim.id)]
        request = ProfileRefreshRequest(
            user_id=agent_seed["owner"],
            report_id=report.id,
            report_revision=1,
            status="failed",
            dispatch_attempts=1,
            last_error="internal_error",
            next_attempt_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(request)
        await db.flush()
        identities = (document.id, claim.id, request.id, report.id)
    return identities


async def invoke(sessions, seed, identities, **kwargs):
    url = sessions.kw["bind"].url
    config = Settings(
        _env_file=None, app_env="local", database_url=url.render_as_string(hide_password=False)
    )
    target = KnowledgeTarget("test", url.host, url.port or 5432, url.database)
    return await module().recover_results(
        sessions,
        config,
        target,
        user_id=seed["owner"],
        document_ids=(identities[0],),
        request_ids=(identities[2],),
        actor="review-test",
        reason="confirmed review findings",
        **kwargs,
    )


async def test_dry_run_then_matching_apply_preserves_originals_and_delivery_limits(
    agent_sessions, agent_seed, recovery_data
):
    document_id, claim_id, request_id, report_id = recovery_data
    plan = await invoke(agent_sessions, agent_seed, recovery_data)
    async with agent_sessions() as db:
        document = await db.get(UserDocument, document_id)
        request = await db.get(ProfileRefreshRequest, request_id)
        assert document.claims_status == "succeeded" and request.status == "failed"
        expires_at = request.expires_at
        original = dict(document.source_snapshot)
    journal = []
    result = await invoke(
        agent_sessions,
        agent_seed,
        recovery_data,
        apply=True,
        expected_sha256=plan["state_sha256"],
        audit=journal.append,
    )
    assert result["mode"] == "applied" and len(journal) == 1
    assert journal[0]["state_sha256"] == plan["state_sha256"]
    async with agent_sessions() as db:
        document = await db.get(UserDocument, document_id)
        request = await db.get(ProfileRefreshRequest, request_id)
        assert document.claims_status == "pending" and document.claims_active_ids == []
        assert document.source_snapshot == original
        assert (await db.get(DocumentClaim, claim_id)).claim_type == "role"
        assert (await db.get(InterviewReport, report_id)).summary == "원본"
        assert request.status == "pending" and request.dispatch_attempts == 1
        assert request.expires_at == expires_at and request.generated_result is None


async def test_changed_state_rejects_the_whole_apply(agent_sessions, agent_seed, recovery_data):
    plan = await invoke(agent_sessions, agent_seed, recovery_data)
    async with agent_sessions.begin() as db:
        document = await db.get(UserDocument, recovery_data[0])
        document.claims_prompt_version = "changed-after-review"
    with pytest.raises(module().RecoveryError):
        await invoke(
            agent_sessions,
            agent_seed,
            recovery_data,
            apply=True,
            expected_sha256=plan["state_sha256"],
            audit=lambda _: None,
        )
    async with agent_sessions() as db:
        assert (await db.get(UserDocument, recovery_data[0])).claims_status == "succeeded"
        assert (await db.get(ProfileRefreshRequest, recovery_data[2])).status == "failed"


@pytest.mark.parametrize("blocked", ["reservation", "expired", "attempts", "revision", "owner"])
async def test_ineligible_rows_are_never_changed(
    agent_sessions, agent_seed, recovery_data, blocked
):
    async with agent_sessions.begin() as db:
        document = await db.get(UserDocument, recovery_data[0])
        request = await db.get(ProfileRefreshRequest, recovery_data[2])
        if blocked == "reservation":
            document.claims_run_id = uuid4()
        elif blocked == "expired":
            request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif blocked == "attempts":
            request.dispatch_attempts = 5
        elif blocked == "revision":
            (await db.get(InterviewReport, recovery_data[3])).current_revision = 2
        else:
            request.user_id = agent_seed["other"]
    with pytest.raises(module().RecoveryError):
        await invoke(agent_sessions, agent_seed, recovery_data)


async def test_failed_audit_write_rolls_back_all_targets(agent_sessions, agent_seed, recovery_data):
    plan = await invoke(agent_sessions, agent_seed, recovery_data)

    def fail(_):
        raise OSError("audit destination unavailable")

    with pytest.raises(OSError):
        await invoke(
            agent_sessions,
            agent_seed,
            recovery_data,
            apply=True,
            expected_sha256=plan["state_sha256"],
            audit=fail,
        )
    async with agent_sessions() as db:
        assert (await db.get(UserDocument, recovery_data[0])).claims_status == "succeeded"
        assert (await db.get(ProfileRefreshRequest, recovery_data[2])).status == "failed"


@pytest.mark.parametrize("status", ["preparing", "preparing_failed", "in_progress"])
async def test_live_interview_documents_are_not_invalidated(
    agent_sessions, agent_seed, recovery_data, status
):
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.status = status
        (await db.get(AnalysisJob, interview.analysis_job_id)).document_id = recovery_data[0]
    with pytest.raises(module().RecoveryError, match="live interview"):
        await invoke(agent_sessions, agent_seed, recovery_data)


async def test_apply_requires_prior_state_and_audit(agent_sessions, agent_seed, recovery_data):
    with pytest.raises(module().RecoveryError, match="Reviewed state"):
        await invoke(agent_sessions, agent_seed, recovery_data, apply=True)


def cli_args(output):
    return [
        "--profile",
        "test",
        "--target-host",
        "127.0.0.1",
        "--target-port",
        "15449",
        "--target-database",
        "recovery_test",
        "--user-id",
        str(uuid4()),
        "--document-id",
        str(uuid4()),
        "--actor",
        "fixture",
        "--reason",
        "confirmed",
        "--output",
        str(output),
    ]


def test_cli_defaults_to_read_only_audit_and_preserves_existing_file(tmp_path, monkeypatch):
    command = module()
    config = Settings(
        _env_file=None,
        app_env="local",
        database_url="postgresql+asyncpg://test:test@127.0.0.1:15449/recovery_test",
    )
    monkeypatch.setattr(command, "Settings", lambda **_: config)
    calls = []

    async def recover(*args, **kwargs):
        calls.append(kwargs)
        assert not kwargs["apply"] and kwargs["expected_sha256"] is None
        return {"mode": "dry_run", "state_sha256": "a" * 64}

    monkeypatch.setattr(command, "recover_results", recover)
    output = tmp_path / "audit.jsonl"
    assert command.main(cli_args(output)) == 0
    first = output.read_bytes()
    assert len(calls) == 1 and b'"mode": "dry_run"' in first
    assert command.main(cli_args(output)) == 1
    assert output.read_bytes() == first and len(calls) == 1


def test_cli_rejects_url_override_before_engine_or_writes(tmp_path, monkeypatch):
    command = module()
    config = Settings(
        _env_file=None,
        app_env="local",
        database_url="postgresql+asyncpg://test:test@127.0.0.1:15449/recovery_test?host=other.invalid",
    )
    monkeypatch.setattr(command, "Settings", lambda **_: config)
    opened = []
    monkeypatch.setattr(command, "create_async_engine", lambda *a, **k: opened.append(a))
    output = tmp_path / "audit.jsonl"
    assert command.main(cli_args(output)) == 1
    assert opened == [] and not output.exists()
