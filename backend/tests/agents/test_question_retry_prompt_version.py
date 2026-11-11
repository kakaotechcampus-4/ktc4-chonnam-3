"""복구 프롬프트 버전의 연결만 검사하며 DB·HTTP는 호출하지 않는다."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from devon_ai import contracts as c

from app.features.interview import question_retry
from app.features.interview.agent_service import QuestionExecution
from tests.agents.director_helpers import settings


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("director_v7", True),
        ("director_v7@legacy", True),
        ("director_v8", True),
        ("director_v8@publication", True),
        ("director_v9", True),
        ("director_v9@candidate", True),
        ("director_v10", True),
        ("director_v11", True),
        ("director_v12", True),
        ("director_v12@candidate", True),
        ("director_v6", False),
        ("director_v80", False),
        ("unregistered", False),
    ],
)
async def test_recovery_prompt_gate_accepts_only_registered_feedback_versions(
    monkeypatch, version, supported
):
    interview_id = uuid4()
    failure = c.CallFailure("semantic", "director_candidate_rewrite", "fixture")
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(
        interview_session_id=interview_id,
        failure={"stage": failure.stage, "error_code": failure.error_code},
        attempts=[{"prompt_version": version}],
    )
    db.scalar.return_value = SimpleNamespace(version=version)
    sessions = MagicMock()
    sessions.return_value.__aenter__ = AsyncMock(return_value=db)
    sessions.return_value.__aexit__ = AsyncMock(return_value=None)
    feedback = SimpleNamespace(recovery=c.CandidateRecovery("rewrite", "fixture"))
    # 타입·출처의 복원 검사는 별도 실제 AI 회귀에서 다룬다. 이 테스트는 버전 게이트만 분리한다.
    monkeypatch.setattr(
        "app.features.interview.question_retry.recovery_feedback_from_attempts",
        Mock(return_value=feedback),
    )
    reserve = AsyncMock(return_value=({}, object()))
    expected = object()
    execute = AsyncMock(return_value=expected)
    monkeypatch.setattr(question_retry, "_reserve", reserve)
    monkeypatch.setattr(question_retry, "_run", execute)
    failed = QuestionExecution(
        turn_id=None,
        call_id=uuid4(),
        failure=failure,
        discard_reason=None,
    )
    result = await question_retry.auto_retry_question(
        sessions, user_id=uuid4(), interview_id=interview_id, failed=failed, settings=settings()
    )
    assert result is expected if supported else result is None
    assert reserve.await_count == execute.await_count == int(supported)
