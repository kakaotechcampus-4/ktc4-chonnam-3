"""선행 후보 선택 결과를 run의 고정된 순위·배치로 저장한다. commit은 호출자가 맡는다."""

from collections.abc import Iterable, Mapping
from dataclasses import fields
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate
from app.db.models.github import Repository
from app.features.analysis.pipeline.steps.repo_select import select_candidates
from app.integrations.github.base import (
    GITHUB_ERROR_RATE_LIMITED,
    GITHUB_ERROR_TOKEN_INVALID,
    RepoDetail,
    RepoSummary,
    filter_reason,
)
from app.shared.enums import Reason


def repository_summary(repository: Repository) -> RepoSummary:
    """DB 자료의 원래 full_name과 공개 상태를 유지해 선행 수집 타입으로 전달한다."""
    return RepoSummary(
        **{field.name: getattr(repository, field.name) for field in fields(RepoSummary)}
    )


async def prepare_candidates(
    session: AsyncSession,
    run_id: UUID,
    *,
    portfolio_full_names: Iterable[str] = (),
    min_size_kb: int,
    contribution_details: Mapping[str, RepoDetail] | None = None,
) -> list[AnalysisRepoCandidate]:
    """사용자 소유 후보와 제외 사유를 한 번 저장하고 같은 run의 기존 자료는 보존한다.

    contribution_details는 호출자가 이번 요청에서 확인한 상세 결과여야 한다. DB의
    synced_at은 목록 동기화도 갱신하므로 커밋 수의 신선도를 증명하지 못한다.
    빈 결과는 표식을 추가하지 않는다. Task 11이 no_public_repo와 단계 완료를 확정하며,
    그 전 새 저장소가 수집되면 빈 결과를 다시 평가할 수 있다.
    """
    await session.flush()
    run = await session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.id == run_id, AnalysisJob.job_type == "analysis_run")
        .with_for_update()
    )
    if run is None:
        raise AppError(Reason.NOT_FOUND)
    existing = list(
        await session.scalars(
            select(AnalysisRepoCandidate)
            .where(AnalysisRepoCandidate.analysis_job_id == run_id)
            .order_by(AnalysisRepoCandidate.base_rank)
        )
    )
    if existing:
        # 분석 ID 등 다른 단계가 저장한 ranking_signals도 덮어쓰지 않는다.
        return existing

    repositories = list(
        await session.scalars(
            select(Repository)
            .where(Repository.user_id == run.user_id)
            .order_by(Repository.pushed_at.desc().nulls_last(), Repository.github_repo_id)
        )
    )
    summaries = {repo.github_repo_id: repository_summary(repo) for repo in repositories}
    canonical_names = {repo.full_name.casefold(): repo.full_name for repo in repositories}
    portfolio = {
        canonical_names.get(name.casefold(), name.casefold()) for name in portfolio_full_names
    }
    details = {name.casefold(): detail for name, detail in (contribution_details or {}).items()}
    inaccessible = {
        repo.github_repo_id
        for repo in repositories
        if not repo.is_accessible
        or (
            repo.full_name.casefold() in details
            and details[repo.full_name.casefold()].repository_inaccessible
        )
    }
    contributions: dict[str, int] = {}
    for repo in repositories:
        detail = details.get(repo.full_name.casefold())
        # README 부분 실패는 성공한 커밋 근거를 지우지 않지만 수집 중단은 구분한다.
        if (
            detail is not None
            and not {GITHUB_ERROR_RATE_LIMITED, GITHUB_ERROR_TOKEN_INVALID}.intersection(
                detail.errors
            )
            and detail.head_sha
            and detail.head_sha == repo.head_sha
            and detail.user_commit_count is not None
            and detail.user_commit_count > 0
            and detail.user_commit_count == repo.user_commit_count
        ):
            contributions[repo.full_name] = detail.user_commit_count
    # 동일 기여도는 기존 base 순서다. 없는 근거를 추정하거나 별·fork 수로 대체하지 않는다.
    contribution_names = sorted(contributions, key=lambda name: -contributions[name])
    selected = {
        item.repo.github_repo_id: item
        for item in select_candidates(
            [
                summaries[repo.github_repo_id]
                for repo in repositories
                if repo.github_repo_id not in inaccessible
            ],
            portfolio_full_names=portfolio,
            high_contribution_full_names=contribution_names,
            min_size_kb=min_size_kb,
        )
    }
    rows: list[AnalysisRepoCandidate] = []
    for rank, repo in enumerate(repositories, start=1):
        summary = summaries[repo.github_repo_id]
        selection = selected.get(repo.github_repo_id)
        signals: dict[str, object] = {
            "ranking_policy": "pushed_at_ordinal_v1",
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "portfolio_mentioned": repo.full_name in portfolio,
            "rule_eligible": repo.github_repo_id not in inaccessible
            and filter_reason(summary, min_size_kb=min_size_kb) is None,
        }
        if repo.full_name in contributions:
            signals["user_commit_count"] = contributions[repo.full_name]
        # 기존 수집 순위를 0~100 안에 표현한다. JD 적합도나 숫자 추천 점수가 아니다.
        score = (Decimal(100) * (len(repositories) - rank + 1) / len(repositories)).quantize(
            Decimal("0.001")
        )
        rows.append(
            AnalysisRepoCandidate(
                analysis_job_id=run_id,
                repository_id=repo.id,
                base_rank=rank,
                batch_no=selection.batch_no if selection else None,
                batch_rank=selection.batch_rank if selection else None,
                selection_reason=selection.selection_reason if selection else None,
                ranking_score=score,
                ranking_signals=signals,
                filter_status=selection.filter_status if selection else "excluded",
                filter_reason=selection.filter_reason
                if selection
                else ("private" if repo.is_private else "inaccessible"),
            )
        )
    session.add_all(rows)
    await session.flush()
    return rows


async def get_batch_candidates(
    session: AsyncSession, run_id: UUID, batch_no: int = 1
) -> list[AnalysisRepoCandidate]:
    """이미 정한 배치의 실행 순서를 반환한다. 제외된 후보는 실행하지 않는다."""
    return list(
        await session.scalars(
            select(AnalysisRepoCandidate)
            .where(
                AnalysisRepoCandidate.analysis_job_id == run_id,
                AnalysisRepoCandidate.filter_status == "eligible",
                AnalysisRepoCandidate.batch_no == batch_no,
            )
            .order_by(AnalysisRepoCandidate.batch_rank, AnalysisRepoCandidate.base_rank)
        )
    )


async def get_remaining_candidates(
    session: AsyncSession, run_id: UUID
) -> list[AnalysisRepoCandidate]:
    """후속 페이지에 배정할 후보를 고정된 기본 순서로 반환한다. 큐를 등록하지 않는다."""
    return list(
        await session.scalars(
            select(AnalysisRepoCandidate)
            .where(
                AnalysisRepoCandidate.analysis_job_id == run_id,
                AnalysisRepoCandidate.filter_status == "eligible",
                AnalysisRepoCandidate.batch_no.is_(None),
            )
            .order_by(AnalysisRepoCandidate.base_rank)
        )
    )
