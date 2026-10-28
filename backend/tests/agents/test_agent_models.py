"""AI 계약의 영구 저장 필드와 PostgreSQL 제약 선언을 확인한다."""

import uuid

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, dialect
from sqlalchemy.schema import CreateTable

from app.db import models


def test_question_contract_and_snapshot_keep_unknown_legacy_values_nullable():
    turns = models.InterviewTurn.__table__.c
    selected = models.SessionRepository.__table__.c
    assert "question_contract" in turns
    assert "snapshot_head_sha" in selected
    assert isinstance(turns.question_contract.type, JSONB)
    assert turns.question_contract.nullable
    assert selected.snapshot_head_sha.nullable
    assert selected.snapshot_head_sha.type.length == 40
    assert turns.question_contract.server_default is None
    assert selected.snapshot_head_sha.server_default is None


def test_evidence_keeps_exact_location_and_optional_summary():
    table = models.Evidence.__table__
    assert {"metadata_key", "summary", "start_line", "end_line"} <= set(table.c.keys())
    evidence = models.Evidence(
        source_type="file",
        path="src/main.py",
        snippet="return result",
        start_line=12,
        end_line=12,
        summary="반환 위치",
    )
    assert evidence.start_line == evidence.end_line == 12
    assert evidence.summary == "반환 위치"
    constraints = {item.name for item in table.constraints if isinstance(item, CheckConstraint)}
    assert "ck_evidences_line_range" in constraints
    ddl = str(CreateTable(table).compile(dialect=dialect()))
    assert "git_ref VARCHAR(40) NOT NULL" in ddl


def test_model_call_failure_can_be_recorded_before_a_turn_exists():
    assert hasattr(models, "LLMCallRecord")
    failure = {"stage": "budget", "error_code": "llm_failed", "reason_summary": "예산 소진"}
    record = models.LLMCallRecord(
        id=uuid.uuid4(),
        interview_session_id=uuid.uuid4(),
        task_name="director_v1",
        attempts=[],
        failure=failure,
    )
    assert record.turn_id is None
    assert record.attempts == []
    assert record.failure == failure
    table = models.LLMCallRecord.__table__
    assert not table.c.interview_session_id.nullable
    assert table.c.turn_id.nullable and table.c.turn_no.nullable
    assert isinstance(table.c.attempts.type, JSONB)
    assert not table.c.attempts.nullable
    assert table.c.discard_reason.nullable
    targets = {item.target_fullname for item in table.foreign_keys}
    assert targets == {"interview_sessions.id", "interview_turns.id"}
