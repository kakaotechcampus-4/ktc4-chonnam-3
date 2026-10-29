"""준비 완료 산출물을 고정 입력에 묶고 재시도에서 외부 작업을 반복하지 않는다."""

import hashlib
import json

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    DomainQuestionFrame,
    Evidence,
    InterviewSession,
    JdRequirement,
    JobPosting,
    PromptVersion,
    RepoAnalysis,
    Repository,
    ScoreCriterion,
    SessionRepository,
)
from app.db.models.report import SCORE_KEYS
from app.features.analysis.analysis_results import resolve_bound_analysis
from app.features.interview.repository_sources import SourcePreparationError


def locked[T: tuple[object, ...]](query: Select[T], enabled: bool) -> Select[T]:
    query = query.execution_options(populate_existing=True)
    return query.with_for_update(read=True) if enabled else query


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def values(row: object, names: str) -> dict[str, object]:
    return {name: getattr(row, name) for name in names.split()}


async def criteria_context(
    db: AsyncSession, row: InterviewSession, *, lock: bool = False
) -> dict[str, object]:
    posting = await db.get(
        JobPosting,
        row.job_posting_id,
        with_for_update={"read": True} if lock else None,
        populate_existing=True,
    )
    assert posting is not None
    criteria = (
        await db.scalars(locked(select(ScoreCriterion).where(ScoreCriterion.is_active), lock))
    ).all()
    frames = (
        await db.scalars(
            locked(
                select(DomainQuestionFrame).where(
                    DomainQuestionFrame.is_active,
                    DomainQuestionFrame.domain_category == (posting.domain_category or "etc"),
                ),
                lock,
            )
        )
    ).all()
    requirements = (
        await db.scalars(
            locked(
                select(JdRequirement).where(JdRequirement.job_posting_id == row.job_posting_id),
                lock,
            )
        )
    ).all()
    return {
        "criteria": sorted(
            [values(item, "id score_key rubric") for item in criteria], key=lambda x: str(x["id"])
        ),
        "frames": sorted(
            [values(item, "id domain_category axis frame_text") for item in frames],
            key=lambda x: str(x["id"]),
        ),
        "requirements": sorted(
            [values(item, "id text category tech_tags") for item in requirements],
            key=lambda x: str(x["id"]),
        ),
    }


async def input_digest(db: AsyncSession, row: InterviewSession, *, lock: bool = False) -> str:
    run = await db.get(
        AnalysisJob,
        row.analysis_job_id,
        with_for_update={"read": True} if lock else None,
        populate_existing=True,
    )
    posting = await db.get(
        JobPosting,
        row.job_posting_id,
        with_for_update={"read": True} if lock else None,
        populate_existing=True,
    )
    selected = (
        await db.execute(
            locked(
                select(SessionRepository, Repository)
                .join(Repository, Repository.id == SessionRepository.repository_id)
                .where(SessionRepository.interview_session_id == row.id)
                .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id),
                lock,
            )
        )
    ).all()
    candidates = (
        await db.scalars(
            locked(
                select(AnalysisRepoCandidate).where(
                    AnalysisRepoCandidate.analysis_job_id == row.analysis_job_id,
                    AnalysisRepoCandidate.repository_id.in_([repo.id for _, repo in selected]),
                ),
                lock,
            )
        )
    ).all()
    l1 = (
        await db.scalars(
            locked(
                select(RepoAnalysis)
                .where(
                    RepoAnalysis.repository_id.in_([repo.id for _, repo in selected]),
                    RepoAnalysis.analysis_level == "l1",
                )
                .order_by(RepoAnalysis.id),
                lock,
            )
        )
    ).all()
    bound = [
        resolve_bound_analysis(candidate, {item.id: item for item in l1})
        for candidate in candidates
    ]
    prompts = (
        await db.scalars(
            locked(
                select(PromptVersion)
                .where(
                    PromptVersion.is_active,
                    PromptVersion.task_name.in_(["repo_deep", "director", "answer_analysis"]),
                )
                .order_by(PromptVersion.task_name, PromptVersion.id),
                lock,
            )
        )
    ).all()
    return digest(
        {
            "owner": row.user_id,
            "run": None
            if run is None
            else values(run, "id user_id job_type status job_posting_id"),
            "posting": None
            if posting is None
            else values(posting, "id parse_status domain_category raw_payload"),
            "repositories": [
                (
                    values(selection, "repository_id snapshot_head_sha is_primary display_order"),
                    values(repo, "id user_id github_repo_id full_name is_private is_accessible"),
                )
                for selection, repo in selected
            ],
            "candidates": sorted(
                [
                    values(item, "repository_id filter_status ranking_signals")
                    for item in candidates
                ],
                key=lambda x: str(x["repository_id"]),
            ),
            "l1": [
                values(item, "id repository_id status head_sha prompt_version result")
                for item in sorted((item for item in bound if item is not None), key=lambda x: x.id)
            ],
            "prompts": [values(item, "task_name version model template") for item in prompts],
            "criteria": await criteria_context(db, row, lock=lock),
        }
    )


async def output_digest(db: AsyncSession, row: InterviewSession, *, lock: bool = False) -> str:
    analyses = (
        await db.scalars(
            locked(
                select(RepoAnalysis)
                .join(
                    SessionRepository, SessionRepository.repository_id == RepoAnalysis.repository_id
                )
                .join(PromptVersion, PromptVersion.version == RepoAnalysis.prompt_version)
                .where(
                    SessionRepository.interview_session_id == row.id,
                    SessionRepository.is_primary,
                    RepoAnalysis.head_sha == SessionRepository.snapshot_head_sha,
                    RepoAnalysis.analysis_level == "l2",
                    PromptVersion.task_name == "repo_deep",
                    PromptVersion.is_active,
                )
                .order_by(RepoAnalysis.id),
                lock,
            )
        )
    ).all()
    evidence = (
        await db.scalars(
            locked(
                select(Evidence)
                .where(Evidence.interview_session_id == row.id, Evidence.tool_name.is_(None))
                .order_by(Evidence.id),
                lock,
            )
        )
    ).all()
    state = row.context_state or {}
    return digest(
        {
            "analyses": [
                values(item, "id repository_id status head_sha prompt_version result notable_areas")
                for item in analyses
            ],
            "evidence": [
                values(item, "id repository_id git_ref path snippet summary start_line end_line")
                for item in evidence
            ],
            "limitations": state.get("preparation_limitations"),
            "repository_limitations": state.get("preparation_repository_limitations"),
        }
    )


async def checked(
    db: AsyncSession, row: InterviewSession, *, lock: bool = False
) -> dict[str, object]:
    saved = (row.context_state or {}).get("preparation_checkpoint")
    fingerprint = await input_digest(db, row, lock=lock)
    if saved is None:
        return {"version": 1, "inputs": fingerprint, "completed": 0}
    if (
        not isinstance(saved, dict)
        or saved.get("version") != 1
        or type(saved.get("completed")) is not int
        or not 0 <= saved["completed"] <= 3
        or saved.get("inputs") != fingerprint
    ):
        raise SourcePreparationError("preparation_inputs_changed")
    if saved["completed"] and saved.get("outputs") != await output_digest(db, row, lock=lock):
        raise SourcePreparationError("preparation_outputs_changed")
    return dict(saved)


def store(row: InterviewSession, checkpoint: dict[str, object]) -> None:
    # JSONB의 중첩 값을 제자리 수정하지 않고 새 객체로 지정한다.
    row.context_state = {
        **(row.context_state or {}),
        "preparation_checkpoint": json.loads(json.dumps(checkpoint, default=str)),
    }


async def complete_analysis(db: AsyncSession, row: InterviewSession) -> None:
    checkpoint = await checked(db, row)
    checkpoint.update(completed=1, outputs=await output_digest(db, row))
    store(row, checkpoint)


async def initialize_personas(
    db: AsyncSession, row: InterviewSession, quota: dict[str, int]
) -> None:
    checkpoint = await checked(db, row)
    if checkpoint["completed"] != 1 or row.current_turn != 0:
        raise SourcePreparationError("preparation_changed")
    context = await criteria_context(db, row)
    if not context["frames"]:
        raise SourcePreparationError("domain_frames_unavailable")
    checkpoint.update(
        completed=2,
        persona_context={
            "counts": dict.fromkeys(quota, 0),
            "quota": quota,
            "frames": context["frames"],
        },
    )
    store(row, checkpoint)


async def initialize_criteria(db: AsyncSession, row: InterviewSession) -> None:
    checkpoint = await checked(db, row)
    if checkpoint["completed"] != 2:
        raise SourcePreparationError("preparation_changed")
    context = await criteria_context(db, row)
    criteria = context["criteria"]
    assert isinstance(criteria, list)
    if {item["score_key"] for item in criteria} != set(SCORE_KEYS) or any(
        not item["rubric"] for item in criteria
    ):
        raise SourcePreparationError("score_criteria_unavailable")
    checkpoint.update(completed=3, criteria_context=context)
    store(row, checkpoint)
