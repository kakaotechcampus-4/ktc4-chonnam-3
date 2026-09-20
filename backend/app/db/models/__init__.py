"""Sprint 1 모델 전체를 metadata 에 등록한다.

Alembic 의 target_metadata 와 mapper 설정이 모든 테이블을 보려면 여기서 한 번씩
import 되어야 한다. 새 모델 모듈을 추가하면 여기에도 추가한다.

docs/db-schema.md / task-02
"""

from app.db.models.analysis import (
    AnalysisJob,
    AnalysisRepoCandidate,
    AnalysisRepoCandidatePage,
    RepoMatchScore,
)
from app.db.models.document import DocumentClaim, UserDocument
from app.db.models.evidence import Evidence, EvidenceConflict, TurnEvidence
from app.db.models.github import RepoAnalysis, Repository, UserProfileSummary
from app.db.models.interview import InterviewSession, InterviewTurn, SessionRepository
from app.db.models.knowledge import DomainQuestionFrame, PromptVersion, ScoreCriterion
from app.db.models.metric import Event
from app.db.models.posting import JdRequirement, JobPosting
from app.db.models.report import InterviewReport, ReportDisagreement, ReportScore
from app.db.models.user import GithubAccount, User

__all__ = [
    "AnalysisJob",
    "AnalysisRepoCandidate",
    "AnalysisRepoCandidatePage",
    "DocumentClaim",
    "DomainQuestionFrame",
    "Event",
    "Evidence",
    "EvidenceConflict",
    "GithubAccount",
    "InterviewReport",
    "InterviewSession",
    "InterviewTurn",
    "JdRequirement",
    "JobPosting",
    "PromptVersion",
    "RepoAnalysis",
    "RepoMatchScore",
    "ReportDisagreement",
    "ReportScore",
    "Repository",
    "ScoreCriterion",
    "SessionRepository",
    "TurnEvidence",
    "User",
    "UserDocument",
    "UserProfileSummary",
]
