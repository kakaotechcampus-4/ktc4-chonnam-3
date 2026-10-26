"""분석 결과·후보 페이지가 함께 사용하는 RepositoryCard 조립."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.features.analysis import queries
from app.features.analysis.analysis_results import resolve_bound_analysis
from app.features.analysis.schemas import LanguageRatio, RepositoryCard
from app.shared.enums import CandidateSource, Reason, RepoStatus


async def get_repository_cards(
    session: AsyncSession, run_id: uuid.UUID, *, batch_no: int = 1
) -> list[RepositoryCard]:
    """미완료 페이지는 NOT_READY. API의 202 전환·enqueue는 Task 11이 맡는다."""
    if batch_no < 1:
        raise AppError(Reason.INVALID_REQUEST)
    # 여러 SELECT 사이에 L1 참조나 추천이 교체되지 않도록 작성 단계의 run 잠금과 맞춘다.
    # 호출자는 카드 조립 직후 읽기 트랜잭션을 끝내야 한다.
    run = await queries.get_run(session, run_id, lock="share")
    candidates = [
        (candidate, repo)
        for candidate, repo in await queries.candidate_repositories(session, run_id)
        if candidate.batch_no == batch_no
        and candidate.filter_status == "eligible"
        and repo.user_id == run.user_id
        and not repo.is_private
        and repo.is_accessible
    ]
    analyses = await queries.bound_analyses(session, [c for c, _ in candidates])
    matches = await queries.run_matches(session, run_id)
    cards = []
    for candidate, repo in sorted(candidates, key=lambda pair: pair[0].batch_rank or 0):
        snapshot = (candidate.ranking_signals or {}).get("analysis")
        match = matches.get(repo.id)
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("status") not in set(RepoStatus)
            or match is None
        ):
            raise AppError(Reason.NOT_READY)
        status = RepoStatus(snapshot["status"])
        valid = resolve_bound_analysis(candidate, analyses) is not None
        if status == RepoStatus.SUCCEEDED and not valid:
            raise AppError(Reason.NOT_READY)
        error_code = snapshot.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            raise AppError(Reason.NOT_READY)
        languages = {name: size for name, size in (repo.languages or {}).items() if size > 0}
        total = sum(languages.values())
        cards.append(
            RepositoryCard(
                id=repo.id,
                name=repo.name,
                full_name=repo.full_name,
                description=repo.description,
                languages=[
                    LanguageRatio(name=name, ratio=round(size / total * 100, 3))
                    for name, size in sorted(
                        languages.items(), key=lambda pair: (-pair[1], pair[0])
                    )
                ],
                topics=repo.topics,
                stars=repo.stars,
                forks=repo.forks,
                commit_count=repo.commit_count,
                user_commit_count=repo.user_commit_count,
                pushed_at=repo.pushed_at,
                status=status,
                error_code=error_code,
                recommended=valid and match.is_recommended,
                candidate_source=CandidateSource(match.candidate_source),
                recommend_reason=match.recommend_reason if valid else None,
                # 점수 미계산은 실패나 0점이 아니다. 성공·부분·실패 모두 null을 명시한다.
                match_score=None,
                matched_requirement_ids=match.matched_requirement_ids if valid else [],
            )
        )
    return cards
