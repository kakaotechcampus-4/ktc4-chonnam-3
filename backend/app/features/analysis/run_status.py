"""기존 7단계와 partial 상태를 공개 계약으로 변환한다."""

from app.db.models.analysis import AnalysisJob
from app.features.analysis.status_schemas import AnalysisRunResponse, AnalysisStep
from app.shared.enums import StepKey, StepStatus, to_run_status


def initial_steps(has_document: bool) -> list[dict[str, object]]:
    return [
        {
            "key": key.value,
            "status": "skipped" if key == StepKey.DOC_EXTRACT and not has_document else "pending",
        }
        for key in StepKey
    ]


def status_response(run: AnalysisJob) -> AnalysisRunResponse:
    saved = {item.get("key"): item.get("status") for item in run.steps}
    steps = [
        AnalysisStep(key=key, status=StepStatus(str(saved.get(key.value, "skipped"))))
        for key in StepKey
    ]
    counted = [step for step in steps if step.status != StepStatus.SKIPPED]
    progress = (
        round(100 * sum(s.status == StepStatus.COMPLETED for s in counted) / len(counted))
        if counted
        else 0
    )
    return AnalysisRunResponse(
        run_id=run.id,
        status=to_run_status(run.status),
        steps=steps,
        progress=progress,
        failure_reason=run.error_code,
        estimated_seconds=run.estimated_seconds,
    )
