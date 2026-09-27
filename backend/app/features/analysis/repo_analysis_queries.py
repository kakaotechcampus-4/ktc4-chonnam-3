"""L0-b/L1 저장 쿼리. 호출한 step이 transaction과 commit을 소유한다."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from devon_ai.contracts import ShallowRepoInput
from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.user import GithubAccount
from app.integrations.github.base import RepoDetail
from app.shared.enums import Reason


async def load_batch(
    session: AsyncSession, run_id: UUID, batch_no: int
) -> tuple[UUID, list[tuple[AnalysisRepoCandidate, Repository]], bool]:
    if batch_no < 1:
        raise AppError(Reason.INVALID_REQUEST)
    job = await session.scalar(
        select(AnalysisJob).where(AnalysisJob.id == run_id, AnalysisJob.job_type == "analysis_run")
    )
    if job is None:
        raise AppError(Reason.NOT_FOUND)
    rows = await session.execute(
        select(AnalysisRepoCandidate, Repository)
        .join(Repository, Repository.id == AnalysisRepoCandidate.repository_id)
        .where(
            AnalysisRepoCandidate.analysis_job_id == run_id,
            AnalysisRepoCandidate.batch_no == batch_no,
            AnalysisRepoCandidate.filter_status == "eligible",
            Repository.user_id == job.user_id,
            Repository.is_private.is_(False),
            Repository.is_accessible.is_(True),
        )
        .order_by(AnalysisRepoCandidate.batch_rank, AnalysisRepoCandidate.base_rank)
    )
    token_status = await session.scalar(
        select(GithubAccount.token_status).where(GithubAccount.user_id == job.user_id)
    )
    return (
        job.user_id,
        [(candidate, repo) for candidate, repo in rows],
        token_status in {"revoked", "invalid"},
    )


async def save_detail(session: AsyncSession, repository_id: UUID, detail: RepoDetail) -> None:
    values: dict[str, object] = {
        "languages": detail.languages,
        "readme_text": detail.readme_text,
        "readme_truncated": detail.readme_truncated,
        "head_sha": detail.head_sha,
        "commit_count": detail.commit_count,
        "user_commit_count": detail.user_commit_count,
    }
    if detail.repository_inaccessible:
        values["is_accessible"] = False
    await session.execute(update(Repository).where(Repository.id == repository_id).values(**values))


async def revoke_token(session: AsyncSession, user_id: UUID, token_encrypted: bytes) -> None:
    """늦은 401이 요청 도중 재연결한 새 토큰을 폐기하지 않도록 호출한 암호문을 대조한다."""
    await session.execute(
        update(GithubAccount)
        .where(
            GithubAccount.user_id == user_id,
            GithubAccount.access_token_encrypted == token_encrypted,
        )
        .values(token_status="revoked")
    )


async def load_cached(
    session: AsyncSession, inputs: Sequence[ShallowRepoInput], prompt_version: str
) -> dict[UUID, RepoAnalysis]:
    if not inputs:
        return {}
    rows = await session.scalars(
        select(RepoAnalysis).where(
            RepoAnalysis.analysis_level == "l1",
            RepoAnalysis.status == "succeeded",
            RepoAnalysis.prompt_version == prompt_version,
            tuple_(RepoAnalysis.repository_id, RepoAnalysis.head_sha).in_(
                [(UUID(item.repository_id), item.head_sha) for item in inputs]
            ),
        )
    )
    return {row.repository_id: row for row in rows}


async def save_analysis(session: AsyncSession, values: Mapping[str, object]) -> UUID:
    """실패한 키는 재시도 결과로 갱신하되 먼저 저장된 성공 결과는 보존한다."""
    statement = insert(RepoAnalysis).values(**values)
    upsert = statement.on_conflict_do_update(
        constraint="uq_repo_analyses_repo_level_sha_prompt",
        set_={
            **{key: getattr(statement.excluded, key) for key in values},
            "updated_at": func.now(),
        },
        where=RepoAnalysis.status != "succeeded",
    ).returning(RepoAnalysis.id)
    analysis_id: UUID | None = await session.scalar(upsert)
    if analysis_id is None:
        analysis_id = await session.scalar(
            select(RepoAnalysis.id).where(
                RepoAnalysis.repository_id == values["repository_id"],
                RepoAnalysis.analysis_level == values["analysis_level"],
                RepoAnalysis.head_sha == values["head_sha"],
                RepoAnalysis.prompt_version == values["prompt_version"],
            )
        )
    assert analysis_id is not None
    return analysis_id


async def bind_snapshots(
    session: AsyncSession,
    run_id: UUID,
    snapshots: Mapping[UUID, dict[str, object]],
    inaccessible: set[UUID],
) -> list[dict[str, object]]:
    """결과 저장 뒤 run을 잠그고 기존 ranking 신호와 같은 키의 성공을 보존한다."""
    await session.execute(select(AnalysisJob.id).where(AnalysisJob.id == run_id).with_for_update())
    candidates = await session.scalars(
        select(AnalysisRepoCandidate)
        .where(
            AnalysisRepoCandidate.analysis_job_id == run_id,
            AnalysisRepoCandidate.repository_id.in_(snapshots),
        )
        .order_by(AnalysisRepoCandidate.batch_rank, AnalysisRepoCandidate.base_rank)
    )
    bound = []
    changed = False
    for candidate in candidates:
        snapshot = snapshots[candidate.repository_id]
        signals = dict(candidate.ranking_signals or {})
        previous = signals.get("analysis")
        if (
            isinstance(previous, dict)
            and previous.get("status") == "succeeded"
            and previous.get("head_sha") == snapshot["head_sha"]
            and previous.get("prompt_version") == snapshot["prompt_version"]
        ):
            snapshot = previous
        changed = changed or previous != snapshot
        signals["analysis"] = snapshot
        candidate.ranking_signals = signals
        if candidate.repository_id in inaccessible:
            changed = (
                changed
                or candidate.filter_status != "excluded"
                or candidate.filter_reason != "inaccessible"
            )
            candidate.filter_status = "excluded"
            candidate.filter_reason = "inaccessible"
        bound.append(snapshot)
    if changed:
        # 추천 상한은 run 전체다. 새 L1과 이전 추천이 섞이지 않도록 재계산 전 조회를 막는다.
        await session.execute(
            delete(RepoMatchScore).where(RepoMatchScore.analysis_job_id == run_id)
        )
    return bound
