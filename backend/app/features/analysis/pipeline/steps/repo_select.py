"""step 2 · 레포 선별. 룰 필터 + 포폴 합집합.
룰 필터: is_fork=false AND is_archived=false AND size_kb>50 AND primary_language IS NOT NULL
        ORDER BY repo_pushed_at DESC LIMIT 10
★ 포폴 언급 레포는 룰 필터를 무조건 우회한다 (사용자가 대표작이라 명시한 것).
  후보 = 룰 필터 10개 ∪ 포폴 언급 레포
★ full_name 매칭 실패(남의 레포·private·삭제·오타)는 정상 상황이다 — 실패 처리하지 않고
  '포폴에 언급된 3개 중 2개를 찾았습니다' 로 알린다.

확정본 §2 룰 필터 / task-08
"""

from dataclasses import dataclass

from app.integrations.github.base import RepoSummary, filter_reason

# analysis_repo_candidates.selection_reason (docs/db-schema.md CANDIDATE_SELECTION_REASONS)
SELECTION_PORTFOLIO_MENTIONED = "portfolio_mentioned"
SELECTION_BASE_RANK_TOP = "base_rank_top"

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


def select_candidates(
    repos: list[RepoSummary],
    *,
    portfolio_full_names: set[str] | None = None,
    min_size_kb: int,
    limit: int = 10,
) -> list[CandidateSelection]:
    """룰 필터 통과 상위 `limit`개 ∪ 포폴 언급 레포를 고른다.

    입력: 전체 public repo 목록(RepoSummary), 포폴에서 매칭된 full_name 집합,
          size_kb 임계값, 상한. 출력: CandidateSelection 목록(base_rank 오름차순).

    base_rank 는 pushed_at 내림차순 전체 순위다 — 포폴 매칭으로 우회한 레포도
    자신의 원래 순위를 유지한다(순위 자체를 조작하지 않는다).
    포폴 full_name 이 실제 레포 목록에 없으면(남의 레포·private·삭제·오타) 그 이름은
    조용히 무시한다 — 호출부가 "N 개 중 M 개를 찾았습니다" 로 안내한다.
    """
    portfolio_full_names = portfolio_full_names or set()
    ranked = sorted(repos, key=_pushed_at_sort_key, reverse=True)

    selections: list[CandidateSelection] = []
    rule_filter_pass_count = 0
    for base_rank, repo in enumerate(ranked, start=1):
        reason = filter_reason(repo, min_size_kb=min_size_kb)
        is_portfolio = repo.full_name in portfolio_full_names

        if reason is None and rule_filter_pass_count < limit:
            rule_filter_pass_count += 1
            selections.append(
                CandidateSelection(
                    repo=repo,
                    base_rank=base_rank,
                    filter_status=FILTER_STATUS_ELIGIBLE,
                    filter_reason=None,
                    selection_reason=SELECTION_BASE_RANK_TOP,
                )
            )
        elif is_portfolio:
            # 포폴 언급 레포는 룰 필터 결과(reason 유무)와 무관하게 후보에 들어간다.
            selections.append(
                CandidateSelection(
                    repo=repo,
                    base_rank=base_rank,
                    filter_status=FILTER_STATUS_ELIGIBLE,
                    filter_reason=None,
                    selection_reason=SELECTION_PORTFOLIO_MENTIONED,
                )
            )
        elif reason is not None:
            selections.append(
                CandidateSelection(
                    repo=repo,
                    base_rank=base_rank,
                    filter_status=FILTER_STATUS_EXCLUDED,
                    filter_reason=reason,
                    selection_reason=None,
                )
            )
        # 룰 필터는 통과했지만 limit 을 넘겨 탈락한 repo 는 이 함수의 반환에 넣지 않는다 —
        # base_rank 산정에는 포함됐으므로 순위 자체는 흔들리지 않는다.

    return selections


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


def _pushed_at_sort_key(repo: RepoSummary) -> tuple[bool, object]:
    """pushed_at 이 없는 repo(NULL)를 정렬 맨 뒤로 보낸다."""
    return (repo.pushed_at is not None, repo.pushed_at)
