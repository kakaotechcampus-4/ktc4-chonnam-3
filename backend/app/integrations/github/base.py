"""Validated public repository metadata; no database or credential storage."""

from datetime import datetime

from pydantic import BaseModel, Field


class GithubApiError(Exception):
    def __init__(self, error_code: str, *, status_code: int | None = None) -> None:
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(error_code)


class RepoSummary(BaseModel):
    github_repo_id: int = Field(alias="id", gt=0, strict=True)
    name: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    description: str | None = None
    primary_language: str | None = Field(default=None, alias="language")
    topics: list[str] = Field(default_factory=list)
    stars: int = Field(default=0, alias="stargazers_count", ge=0)
    forks: int = Field(default=0, alias="forks_count", ge=0)
    size_kb: int = Field(default=0, alias="size", ge=0)
    default_branch: str | None = None
    is_private: bool = Field(alias="private", strict=True)
    is_fork: bool = Field(default=False, alias="fork")
    is_archived: bool = Field(default=False, alias="archived")
    pushed_at: datetime | None = None
