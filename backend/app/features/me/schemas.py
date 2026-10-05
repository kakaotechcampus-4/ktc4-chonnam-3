"""Explicit public views; OAuth credentials cannot enter these responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.shared.schema import CamelModel


class MeResponse(CamelModel):
    name: str
    avatar_url: str | None
    github_linked: bool


class GithubProfile(CamelModel):
    linked: bool
    login: str | None
    public_repo_count: int | None


class InterviewStats(CamelModel):
    total_count: int
    average_score: float | None


class MeProfileResponse(CamelModel):
    name: str
    avatar_url: str
    login_id: str | None
    joined_at: datetime
    desired_position: str | None
    github: GithubProfile
    interview_summary: InterviewStats


class LanguageRatio(CamelModel):
    name: str
    ratio: float


class AnalysisPanel(CamelModel):
    based_on_repo_count: int
    languages: list[LanguageRatio]
    project_types: list[str]
    role_summary: str


class RecentInterview(CamelModel):
    id: UUID
    position: str
    company_name: str | None
    total_score: float | None
    completed_at: datetime | None


class HomeResponse(CamelModel):
    name: str
    github_linked: bool
    repository_count: int
    analysis_status: Literal["syncing", "no_repository", "no_interview", "completed"]
    analysis: AnalysisPanel | None
    recent_interviews: list[RecentInterview]


class InterviewSummary(RecentInterview):
    tech_stack: list[str]
    career_level: str
    repository_names: list[str]
    status: Literal["preparing", "preparing_failed", "in_progress", "completed", "abandoned"]
    started_at: datetime | None


class InterviewListResponse(CamelModel):
    interviews: list[InterviewSummary]
    total: int
    page: int
    size: int
    average_score: float | None
