"""Sprint 1 모델 registry. Alembic 과 테스트가 이 모듈로 metadata 를 채운다.

이번 작업 범위(공고 입력 · repo 수집 · 진행률 폴링)에 필요한 테이블만 등록한다.
면접/근거/리포트/지식/지표 모델은 각 task 에서 추가한다.
"""

from app.db.models.analysis import (
    AnalysisJob,
    AnalysisRepoCandidate,
    AnalysisRepoCandidatePage,
    RepoMatchScore,
)
from app.db.models.document import UserDocument
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.posting import JdRequirement, JobPosting
from app.db.models.user import GithubAccount, User

__all__ = [
    "AnalysisJob",
    "AnalysisRepoCandidate",
    "AnalysisRepoCandidatePage",
    "GithubAccount",
    "JdRequirement",
    "JobPosting",
    "RepoAnalysis",
    "RepoMatchScore",
    "Repository",
    "User",
    "UserDocument",
]
