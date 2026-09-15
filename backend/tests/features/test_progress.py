"""진행률 계산과 DB status -> FE RunStatus 매핑."""

from app.features.analysis.progress import compute_progress, initial_steps
from app.shared.enums import (
    JOB_STATUS_TO_RUN_STATUS,
    STEP_ORDER,
    JobStatus,
    RunStatus,
    StepKey,
    StepStatus,
)


def test_initial_steps_has_seven_pending_steps() -> None:
    steps = initial_steps()
    assert list(steps) == [str(key) for key in STEP_ORDER]
    assert set(steps.values()) == {str(StepStatus.PENDING)}
    assert compute_progress(steps) == 0


def test_progress_counts_finished_and_half_of_running() -> None:
    steps = initial_steps()
    steps[str(StepKey.DOC_EXTRACT)] = str(StepStatus.SUCCEEDED)
    steps[str(StepKey.REPO_SELECT)] = str(StepStatus.SUCCEEDED)
    steps[str(StepKey.REPO_DETAIL)] = str(StepStatus.RUNNING)
    # 2 step 완료(28.6) + running 0.5 step(7.1) = 36
    assert compute_progress(steps) == 36

    for key in STEP_ORDER:
        steps[str(key)] = str(StepStatus.SUCCEEDED)
    assert compute_progress(steps) == 100


def test_failed_step_counts_as_finished() -> None:
    steps = initial_steps()
    steps[str(StepKey.DOC_EXTRACT)] = str(StepStatus.FAILED)
    assert compute_progress(steps) == 14


def test_partial_maps_to_failed_for_frontend() -> None:
    assert JOB_STATUS_TO_RUN_STATUS[JobStatus.PARTIAL] is RunStatus.FAILED
    assert JOB_STATUS_TO_RUN_STATUS[JobStatus.SUCCEEDED] is RunStatus.COMPLETED
    assert JOB_STATUS_TO_RUN_STATUS[JobStatus.QUEUED] is RunStatus.RUNNING
    assert JOB_STATUS_TO_RUN_STATUS[JobStatus.CANCELED] is RunStatus.FAILED
