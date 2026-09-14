"""repositories, repo_analyses, user_profile_summaries.

docs/layer-rules.md 1절 / task-02

repo_analyses 는 AI L1/L2 분석 결과가 들어오는 자리다. BE 는 행을 읽어 카드로 옮길 뿐
분석 자체를 수행하지 않는다 (AI 패키지 담당).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Repository(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """public repo 의 L0-a(목록) · L0-b(상세) 수집 결과.

    is_private 는 필드만 유지하고 분석/선택 대상에서 제외한다.
    """

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("user_id", "github_repo_id", name="uq_repositories_user_github_repo"),
        UniqueConstraint("user_id", "full_name", name="uq_repositories_user_full_name"),
        CheckConstraint("fetch_level IN ('list','detail')", name="repositories_fetch_level"),
        Index("ix_repositories_user_pushed_at", "user_id", "repo_pushed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(200))

    # ── L0-a: 목록 API 응답에 이미 들어있는 필드 ──────────────────────
    primary_language: Mapped[str | None] = mapped_column(String(100))
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    stars: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    forks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    repo_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repo_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── L0-b: 후보로 승격된 repo 만 추가 수집 ─────────────────────────
    languages: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    readme_text: Mapped[str | None] = mapped_column(Text)
    readme_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    head_sha: Mapped[str | None] = mapped_column(String(40))
    commit_count: Mapped[int | None] = mapped_column(Integer)
    user_commit_count: Mapped[int | None] = mapped_column(Integer)

    fetch_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'list'")
    )
    fetch_error_code: Mapped[str | None] = mapped_column(String(50))
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RepoAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """AI 가 만든 repo 분석 결과의 저장 자리.

    캐시 키는 (repository_id, analysis_level, head_sha, prompt_version) 이다.
    model 은 UNIQUE 에 넣지 않는다 (docs/db-schema.md).
    """

    __tablename__ = "repo_analyses"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "analysis_level",
            "head_sha",
            "prompt_version",
            name="uq_repo_analyses_cache_key",
        ),
        CheckConstraint("analysis_level IN ('shallow','deep')", name="repo_analyses_level"),
        CheckConstraint("status IN ('succeeded','partial','failed')", name="repo_analyses_status"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_level: Mapped[str] = mapped_column(String(20), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[str | None] = mapped_column(Text)
    tech_stack: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    notable_areas: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    batch_position: Mapped[int | None] = mapped_column(SmallInteger)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
