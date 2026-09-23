"""repositories, repo_analyses, user_profile_summaries.

docs/layer-rules.md 1절 / task-02
"""

import uuid
from datetime import datetime

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
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, check_in

# L0-a/L0-b 는 metadata 수집 단계라 행을 남기지 않는다. LLM 분석만 여기 기록한다.
ANALYSIS_LEVELS = ("l1", "l2")
# openapi RepoStatus 와 같은 집합. 행은 분석 종료 시점에 넣는다.
REPO_ANALYSIS_STATUSES = ("succeeded", "partial", "failed")


class Repository(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """수집한 GitHub repo. private 는 필드만 유지하고 분석/선택 대상에서 제외한다."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("user_id", "github_repo_id", name="uq_repositories_user_github_repo"),
        Index("ix_repositories_user_id_pushed_at", "user_id", "pushed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # L0-b 수집분
    primary_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_commit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # README 는 길이 상한을 두고 저장한다. 잘렸으면 readme_truncated 로 표시한다.
    readme_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    readme_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    stars: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    forks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    default_branch: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # 삭제·private 전환·권한 상실이면 false. retry 의 repository_unavailable 판정에 쓴다.
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepoAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """repo LLM 분석 결과. L1 shallow / L2 deep.

    UNIQUE 가 자연 멱등 키다 — 워커가 중복 실행돼도 ON CONFLICT DO NOTHING 으로 넘긴다.
    model 은 UNIQUE 에 넣지 않는다 (docs/db-schema.md 주요 결정).
    """

    __tablename__ = "repo_analyses"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "analysis_level",
            "head_sha",
            "prompt_version",
            name="uq_repo_analyses_repo_level_sha_prompt",
        ),
        CheckConstraint(check_in("analysis_level", ANALYSIS_LEVELS), name="repo_analyses_level"),
        CheckConstraint(check_in("status", REPO_ANALYSIS_STATUSES), name="repo_analyses_status"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_level: Mapped[str] = mapped_column(String(2), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # 어느 모델로 만든 결과인지를 행이 스스로 증명한다. 코드 상수로 고정하지 않는다.
    model: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 첫 batch 안에서의 위치. 후보 page 재구성에 쓴다.
    batch_position: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    # L2 전용. [{path, reason, ...}] — Evidence Retriever 가 이 path 주변을 읽는다.
    notable_areas: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    # LLM 호출 메타 (docs/layer-rules.md LLM 규칙)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")


class UserProfileSummary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """사용자 프로필 집계. 전체 수집 repo 가 아니라 완료된 면접에 사용된 repo 기준이다."""

    __tablename__ = "user_profile_summaries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # ⚠ 정렬해서 저장한다. 재생성 판정 키라서 순서가 흔들리면 매번 재생성된다.
    based_repo_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    based_on_repo_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # [{name, ratio}] — openapi LanguageRatio 와 같은 모양
    languages: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    project_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    role_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
