"""분석 요청/응답 스키마의 구현 예정 경계.
★ run 조회는 HTTP 200에서 status와 failureReason으로 분석 실패를 표현한다.
  생성 성공은 202 {runId}, 동일 fingerprint의 진행 중 run은 409 run_in_progress와
  error.details.runId를 반환한다. 요청 오류와 run 처리 실패를 구분한다.
★ failureReason 은 BE 내부명을 그대로 쓴다 (FE 합의) — jd_fetch_failed /
  jd_extraction_failed / token_invalid. 경계 매핑 레이어를 두지 않는다.
★ DB partial은 FE failed로 매핑한다. partial 결과 조회는 허용하며
  analyzedCount, failedCount, failedRepositories를 포함한다.
★ 응답 필드·enum은 spec/shared/contracts/openapi.yaml을 따른다.

확정본 §3 / task-04
"""

import uuid
from datetime import datetime

from app.shared.enums import CandidateSource, RepoStatus
from app.shared.schema import CamelResponse


class LanguageRatio(CamelResponse):
    name: str
    ratio: float


class RepositoryCard(CamelResponse):
    """Task 10의 공통 카드. 필수 nullable 필드는 응답에서 생략하지 않는다."""

    id: uuid.UUID
    name: str
    full_name: str
    description: str | None
    languages: list[LanguageRatio]
    topics: list[str]
    stars: int
    forks: int
    commit_count: int | None
    user_commit_count: int | None
    pushed_at: datetime | None
    status: RepoStatus
    error_code: str | None
    recommended: bool
    candidate_source: CandidateSource
    recommend_reason: str | None
    match_score: float | None
    matched_requirement_ids: list[uuid.UUID]
