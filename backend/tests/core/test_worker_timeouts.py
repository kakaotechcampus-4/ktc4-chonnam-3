"""긴 준비·리포트 작업만 별도 ARQ 제한을 사용한다."""

from arq.worker import Worker

from app.features.interview.prepare_lease import JOB_TIMEOUT_SECONDS
from app.workers.arq_app import WorkerSettings


async def test_registered_jobs_keep_names_and_scope_long_timeouts():
    worker = Worker(
        WorkerSettings.functions, job_timeout=WorkerSettings.job_timeout, handle_signals=False
    )
    assert {"initial_sync", "interview_prep", "report_generate"} <= set(worker.functions)
    assert WorkerSettings.job_timeout == 600
    assert worker.functions["interview_prep"].timeout_s == JOB_TIMEOUT_SECONDS == 1800
    assert worker.functions["report_generate"].timeout_s == 1800
    assert worker.functions["initial_sync"].timeout_s is None
    if "profile_summary" in worker.functions:
        assert worker.functions["profile_summary"].timeout_s is None


def test_legacy_two_argument_preparation_budget_remains_compatible():
    import pytest

    from app.features.interview.prepare_lease import PreparationTimeoutError, validate_timeout

    # 구형 호출은 600초와 4T를 유지하고 신규 작업의 1770초 경로와 분리한다.
    validate_timeout(30, 127.5)
    with pytest.raises(PreparationTimeoutError):
        validate_timeout(30, 127.6)


def test_legacy_claim_expiry_keeps_the_original_worker_grace():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.features.interview.prepare_lease import expires

    updated = datetime.now(UTC)
    row = SimpleNamespace(context_state={}, updated_at=updated)
    assert expires(row) == updated + timedelta(seconds=600)


def test_explicit_document_and_claim_budgets_are_included():
    import pytest

    from app.features.interview.prepare_lease import PreparationTimeoutError, validate_timeout

    with pytest.raises(PreparationTimeoutError):
        validate_timeout(30, 200, deep_seconds=200, claim_seconds=200, document_seconds=200)
