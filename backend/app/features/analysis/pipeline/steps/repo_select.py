"""step 2 · 전체 후보를 보존하면서 첫 분석 배치를 고른다."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.integrations.github.base import (
    FILTER_INACCESSIBLE,
    FILTER_PRIVATE,
    RepoDetail,
    RepoSummary,
    filter_reason,
)

# analysis_repo_candidates.selection_reason (docs/db-schema.md CANDIDATE_SELECTION_REASONS)
SELECTION_PORTFOLIO_MENTIONED = "portfolio_mentioned"
SELECTION_BASE_RANK_TOP = "base_rank_top"
SELECTION_HIGH_CONTRIBUTION = "high_contribution"

FILTER_STATUS_ELIGIBLE = "eligible"
FILTER_STATUS_EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """analysis_repo_candidates 한 행에 대응한다. base_rank 는 전체 public repo 순위다."""

    repo: RepoSummary
    base_rank: int
    filter_status: str
    filter_reason: str | None
    selection_reason: str | None
    batch_no: int | None = None
    batch_rank: int | None = None


def select_candidates(
    repos: list[RepoSummary],
    *,
    portfolio_full_names: set[str] | None = None,
    high_contribution_full_names: Sequence[str] = (),
    min_size_kb: int,
    limit: int = 10,
) -> list[CandidateSelection]:
    """포트폴리오 최대 3개, 기본 순위 최대 5개, 기여도 최대 2개를 중복 제거한다.

    기여도 목록은 호출부가 근거로 정렬한 순서다. 없으면 임의로 채우지 않는다.
    base_rank는 기존 pushed_at 순위이며, task-10의 종합 점수 계산은 포함하지 않는다.
    반환 목록은 첫 배치 밖의 후보와 제외 후보까지 base_rank 순서로 모두 유지한다.
    상세 수집 호출부는 eligible이면서 batch_no == 1인 후보만 골라야 한다.

    포트폴리오 언급 레포는 fork/archived/no_language/too_small 을 우회한다 — 사용자가
    명시한 대표작이기 때문이다. private 만은 예외 없이 제외한다(0001 결정).
    """
    if not 0 <= limit <= 10:
        raise ValueError("first batch limit must be between 0 and 10")
    portfolio_full_names = portfolio_full_names or set()
    ranked = sorted(repos, key=_pushed_at_sort_key, reverse=True)

    selections: list[CandidateSelection] = []
    for base_rank, repo in enumerate(ranked, start=1):
        reason = filter_reason(repo, min_size_kb=min_size_kb)
        is_portfolio = repo.full_name in portfolio_full_names
        if reason is not None and reason != FILTER_PRIVATE and is_portfolio:
            # 포트폴리오 언급은 private 을 제외한 나머지 제외 사유를 우회한다.
            reason = None
        selections.append(
            CandidateSelection(
                repo=repo,
                base_rank=base_rank,
                filter_status=FILTER_STATUS_ELIGIBLE if reason is None else FILTER_STATUS_EXCLUDED,
                filter_reason=reason,
                selection_reason=None,
            )
        )

    eligible_names = [
        s.repo.full_name for s in selections if s.filter_status == FILTER_STATUS_ELIGIBLE
    ]
    eligible_set = set(eligible_names)
    portfolio = [name for name in eligible_names if name in portfolio_full_names][:3]
    contribution = [
        name for name in dict.fromkeys(high_contribution_full_names) if name in eligible_set
    ][:2]
    batch: dict[str, tuple[int, str]] = {}
    for names, selection_reason in (
        (portfolio, SELECTION_PORTFOLIO_MENTIONED),
        (eligible_names[:5], SELECTION_BASE_RANK_TOP),
        (contribution, SELECTION_HIGH_CONTRIBUTION),
    ):
        for name in names:
            if name not in batch and len(batch) < limit:
                batch[name] = (len(batch) + 1, selection_reason)

    return [
        replace(
            s,
            batch_no=1,
            batch_rank=batch[s.repo.full_name][0],
            selection_reason=batch[s.repo.full_name][1],
        )
        if s.repo.full_name in batch
        else s
        for s in selections
    ]


def matched_portfolio_count(
    selections: list[CandidateSelection], portfolio_full_names: set[str]
) -> tuple[int, int]:
    """포폴 언급 레포 중 실제로 찾은 개수. 입력: 선택 결과, 포폴 full_name 집합.

    출력: (찾은 개수, 전체 포폴 언급 개수). 안내 문구 조립은 호출부(service) 몫이다.
    """
    matched = {
        selection.repo.full_name
        for selection in selections
        if selection.repo.full_name in portfolio_full_names
    }
    return len(matched), len(portfolio_full_names)


def reclassify_inaccessible(
    selections: list[CandidateSelection], details: dict[str, RepoDetail]
) -> list[CandidateSelection]:
    """repo_detail(step 3) 결과를 보고 eligible 후보 중 사라진 레포를 excluded/inaccessible 로
    내린다.

    입력: select_candidates() 결과, {full_name: RepoDetail}(repo_detail.collect_repo_details 출력).
    출력: 갱신된 CandidateSelection 목록(base_rank·순서는 그대로 유지).

    룰 필터·포폴 매칭 시점에는 레포가 있었더라도, repo_detail 이 실제로 불러본 시점에
    삭제·private 전환·권한 상실로 전부 실패할 수 있다(base.py FILTER_INACCESSIBLE 의
    "실제 호출이 실패해야 알 수 있다"가 이 지점이다). rate limit 로 아직 확인 못 했거나
    README 만 없는 경우는 inaccessible 이 아니다 — is_inaccessible() 이 이를 구분한다.
    """
    updated: list[CandidateSelection] = []
    for selection in selections:
        detail = details.get(selection.repo.full_name)
        if (
            selection.filter_status == FILTER_STATUS_ELIGIBLE
            and detail is not None
            and is_inaccessible(detail)
        ):
            # 제외 여부만 바꾸고 수집을 시도한 배치와 당시 선택 근거는 보존한다.
            updated.append(
                replace(
                    selection,
                    filter_status=FILTER_STATUS_EXCLUDED,
                    filter_reason=FILTER_INACCESSIBLE,
                )
            )
        else:
            updated.append(selection)
    return updated


def is_inaccessible(detail: RepoDetail) -> bool:
    """일시 오류나 README 부재가 아닌, 클라이언트가 확인한 접근 불가만 반영한다."""
    return detail.repository_inaccessible


def _pushed_at_sort_key(repo: RepoSummary) -> tuple[bool, object]:
    """pushed_at 이 없는 repo(NULL)를 정렬 맨 뒤로 보낸다."""
    return (repo.pushed_at is not None, repo.pushed_at)
