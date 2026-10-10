"""run 후보에 고정한 L1 참조를 검증한다. 최신 캐시로 실패 기록을 대체하지 않는다."""

from collections.abc import Mapping
from uuid import UUID

from app.db.models.analysis import AnalysisRepoCandidate
from app.db.models.github import RepoAnalysis


def resolve_bound_analysis(
    candidate: AnalysisRepoCandidate, analyses: Mapping[UUID, RepoAnalysis]
) -> RepoAnalysis | None:
    """같은 저장소·SHA·prompt의 성공 L1만 매칭과 선택에 사용할 수 있다."""
    snapshot = (candidate.ranking_signals or {}).get("analysis")
    if not isinstance(snapshot, dict) or snapshot.get("status") != "succeeded":
        return None
    raw_id = snapshot.get("analysis_id")
    if not isinstance(raw_id, str):
        return None
    try:
        analysis_id = UUID(raw_id)
    except ValueError:
        return None
    analysis = analyses.get(analysis_id)
    if (
        analysis is None
        or analysis.id != analysis_id
        or analysis.repository_id != candidate.repository_id
        or analysis.analysis_level != "l1"
        or analysis.status != "succeeded"
        or analysis.head_sha != snapshot.get("head_sha")
        or analysis.prompt_version != snapshot.get("prompt_version")
    ):
        return None
    return analysis
