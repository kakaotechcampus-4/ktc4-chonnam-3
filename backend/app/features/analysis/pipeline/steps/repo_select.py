"""step 2 · 레포 선별. 룰 필터 + 포폴 합집합 -> analysis_repo_candidates.

룰 필터: is_private=false AND is_fork=false AND is_archived=false
        AND size_kb > REPO_MIN_SIZE_KB AND primary_language IS NOT NULL
포폴 언급 레포는 룰 필터를 우회한다 (사용자가 대표작이라 명시한 것). 단 private 는 제외한다.
full_name 매칭 실패(남의 레포·private·삭제·오타)는 정상 상황이라 실패 처리하지 않는다.

첫 batch 구성은 포폴 언급 최대 3개 + base_rank 상위로 채워 최대 10개다.
`jd_signal`(JD 수집 이후에야 알 수 있음)과 `high_contribution`(L0-b 이후에야 알 수 있음)
버킷은 현재 단계 순서에서 계산할 수 없다 — later.md AI-L05 결정 대기.

spec/backend/features/analysis-run.md Candidate Ranking / task-08
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models.analysis import AnalysisRepoCandidate, AnalysisRepoCandidatePage
from app.db.models.github import Repository
from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.features.analysis.pipeline.initial_sync import sync_user_repositories
from app.integrations.github.client import (
    GithubError,
    GithubRateLimited,
    GithubTokenInvalid,
)
from app.shared.clock import now
from app.shared.enums import (
    CandidatePageStatus,
    FilterReason,
    FilterStatus,
    JobErrorCode,
    SelectionReason,
)

logger = structlog.get_logger(__name__)

MAX_PORTFOLIO_IN_FIRST_BATCH = 3
MAX_BASE_RANK_TOP_IN_FIRST_BATCH = 5
_RECENCY_HORIZON_DAYS = 730.0
_STAR_CAP = 50.0
_SIZE_CAP_KB = 5_000.0


@dataclass(frozen=True)
class ScoredRepo:
    """랭킹 계산 결과 1건."""

    repository: Repository
    score: float
    filter_reason: FilterReason | None
    portfolio_mentioned: bool

    @property
    def eligible(self) -> bool:
        return self.filter_reason is None


async def run(ctx: RunContext) -> None:
    """전체 public repo 에 대해 base_rank 를 매기고 첫 batch 10개를 고른다."""
    settings = get_settings()
    repos = await queries.list_user_repositories(ctx.db, ctx.user.id)
    if not repos:
        # 연동 직후 initial_sync(repo_sync) 가 아직 돌지 않은 경우의 안전망.
        # 같은 pipeline 함수를 그대로 호출한다 (로직 중복 금지).
        repos = await _sync_then_reload(ctx)
    if not repos:
        raise StepFailed(JobErrorCode.NO_PUBLIC_REPO)

    mentioned = {name.lower() for name in ctx.portfolio_full_names}
    scored = sorted(
        (_score(repo, mentioned, settings.repo_min_size_kb) for repo in repos),
        key=lambda item: (-item.score, item.repository.full_name),
    )
    eligible = [item for item in scored if item.eligible]
    if not eligible:
        raise StepFailed(JobErrorCode.NO_PUBLIC_REPO)

    batch = _first_batch(eligible, settings.repo_candidate_limit)
    batch_reason = {item.repository.id: reason for item, reason in batch}

    # 재실행 idempotency — 이 run 의 후보를 다시 만든다.
    await ctx.db.execute(
        delete(AnalysisRepoCandidate).where(AnalysisRepoCandidate.analysis_job_id == ctx.job.id)
    )

    batch_rank = {item.repository.id: idx + 1 for idx, (item, _) in enumerate(batch)}
    for base_rank, item in enumerate(scored, start=1):
        in_batch = item.repository.id in batch_reason
        ctx.db.add(
            AnalysisRepoCandidate(
                analysis_job_id=ctx.job.id,
                repository_id=item.repository.id,
                base_rank=base_rank,
                batch_no=1 if in_batch else None,
                batch_rank=batch_rank.get(item.repository.id),
                selection_reason=str(batch_reason.get(item.repository.id, SelectionReason.OTHER)),
                ranking_score=round(item.score, 3),
                ranking_signals=_signals(item, settings.repo_min_size_kb),
                filter_status=str(
                    FilterStatus.ELIGIBLE if item.eligible else FilterStatus.EXCLUDED
                ),
                filter_reason=str(item.filter_reason) if item.filter_reason else None,
            )
        )

    existing_page = await queries.get_candidate_page(ctx.db, ctx.job.id, 1)
    if existing_page is None:
        ctx.db.add(
            AnalysisRepoCandidatePage(
                analysis_job_id=ctx.job.id,
                page_no=1,
                status=str(CandidatePageStatus.RUNNING),
                requested_at=now(),
            )
        )
    await ctx.db.commit()

    ctx.batch_repository_ids = [item.repository.id for item, _ in batch]
    logger.info(
        "repo_select_done",
        run_id=str(ctx.job.id),
        total=len(scored),
        eligible=len(eligible),
        batch=len(batch),
    )


async def _sync_then_reload(ctx: RunContext) -> list[Repository]:
    """repositories 가 비어 있으면 L0-a 를 즉시 수집한다."""
    try:
        await sync_user_repositories(ctx.db, ctx.user.id)
    except GithubTokenInvalid as exc:
        raise StepFailed(JobErrorCode.TOKEN_INVALID) from exc
    except GithubRateLimited as exc:
        raise StepFailed(JobErrorCode.RATE_LIMITED) from exc
    except GithubError as exc:
        logger.warning("repo_select_sync_failed", run_id=str(ctx.job.id), error=str(exc))
        return []
    return await queries.list_user_repositories(ctx.db, ctx.user.id)


def _score(repo: Repository, mentioned: set[str], min_size_kb: int) -> ScoredRepo:
    """L0-a 신호만으로 매기는 결정적 점수 (LLM 아님)."""
    portfolio = repo.full_name.lower() in mentioned
    reason = _filter_reason(repo, min_size_kb, portfolio)
    days = _days_since_push(repo)
    recency = max(0.0, 1.0 - days / _RECENCY_HORIZON_DAYS)
    stars = min(repo.stars, int(_STAR_CAP)) / _STAR_CAP
    size = min(repo.size_kb, int(_SIZE_CAP_KB)) / _SIZE_CAP_KB
    meta = 1.0 if (repo.description or repo.topics) else 0.0
    score = 0.5 * recency + 0.2 * stars + 0.2 * size + 0.1 * meta
    if portfolio:
        # 사용자가 대표작이라고 명시한 레포는 항상 상위에 둔다.
        score += 1.0
    return ScoredRepo(
        repository=repo, score=score, filter_reason=reason, portfolio_mentioned=portfolio
    )


def _filter_reason(
    repo: Repository, min_size_kb: int, portfolio_mentioned: bool
) -> FilterReason | None:
    if repo.is_private:
        return FilterReason.PRIVATE
    if portfolio_mentioned:
        return None
    if repo.is_fork:
        return FilterReason.FORK
    if repo.is_archived:
        return FilterReason.ARCHIVED
    if not repo.primary_language:
        return FilterReason.NO_LANGUAGE
    if repo.size_kb <= min_size_kb:
        return FilterReason.TOO_SMALL
    return None


def _days_since_push(repo: Repository) -> float:
    if repo.repo_pushed_at is None:
        return _RECENCY_HORIZON_DAYS
    return max(0.0, (now() - repo.repo_pushed_at).total_seconds() / 86_400)


def _first_batch(
    eligible: list[ScoredRepo], limit: int
) -> list[tuple[ScoredRepo, SelectionReason]]:
    """혼합 전략으로 첫 batch 를 만든다.

    포폴 언급 최대 3개 + base_rank 상위 최대 5개 + 나머지는 rank 순 채움.
    `jd_signal`(JD 는 step 4)과 `high_contribution`(L0-b 는 step 3) 버킷은 이 시점에
    계산할 수 없어 비운다 — later.md AI-L05.
    """
    batch: list[tuple[ScoredRepo, SelectionReason]] = []
    seen: set[uuid.UUID] = set()

    for item in (i for i in eligible if i.portfolio_mentioned):
        if len(batch) >= min(MAX_PORTFOLIO_IN_FIRST_BATCH, limit):
            break
        batch.append((item, SelectionReason.PORTFOLIO_MENTIONED))
        seen.add(item.repository.id)

    rest = [i for i in eligible if i.repository.id not in seen and not i.portfolio_mentioned]
    for index, item in enumerate(rest):
        if len(batch) >= limit:
            break
        reason = (
            SelectionReason.BASE_RANK_TOP
            if index < MAX_BASE_RANK_TOP_IN_FIRST_BATCH
            else SelectionReason.OTHER
        )
        batch.append((item, reason))
        seen.add(item.repository.id)
    return batch


def _signals(item: ScoredRepo, min_size_kb: int) -> dict[str, object]:
    """카드의 candidateSource 판정에 쓰는 신호. 포폴 우회 여부를 구분해 둔다."""
    repo = item.repository
    return {
        "portfolio_mentioned": item.portfolio_mentioned,
        "rule_filter_passed": _filter_reason(repo, min_size_kb, False) is None,
        "days_since_push": round(_days_since_push(repo), 1),
        "stars": repo.stars,
        "size_kb": repo.size_kb,
        "primary_language": repo.primary_language,
    }
