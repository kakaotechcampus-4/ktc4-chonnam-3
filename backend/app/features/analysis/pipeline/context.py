"""analysis_run 7 step 이 주고받는 작업 컨텍스트와 단계 실패 타입.

step 함수는 DB 세션과 job 행을 이 컨텍스트로만 받는다 (docs/layer-rules.md 1절).
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisJob
from app.db.models.user import GithubAccount, User
from app.shared.enums import JobErrorCode


class StepFailed(Exception):
    """해당 step 에서 run 을 더 진행할 수 없을 때. job.error_code 로 그대로 남는다."""

    def __init__(self, error_code: JobErrorCode, *, message: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message or str(error_code))


@dataclass
class RunContext:
    """run 1회의 작업 상태. 원본은 항상 Postgres 이고 여기에는 중간 결과만 둔다."""

    db: AsyncSession
    job: AnalysisJob
    user: User
    github_account: GithubAccount | None = None
    #: 포트폴리오에서 뽑은 owner/repo 목록 (doc_extract 결과)
    portfolio_full_names: list[str] = field(default_factory=list)
    #: 첫 batch 후보 repository_id (repo_select 결과)
    batch_repository_ids: list[uuid.UUID] = field(default_factory=list)
    #: L0-b 수집에 실패한 repo (repo_detail 결과) -> partial 판정 근거
    failed_repository_ids: dict[uuid.UUID, str] = field(default_factory=dict)
    job_posting_id: uuid.UUID | None = None
