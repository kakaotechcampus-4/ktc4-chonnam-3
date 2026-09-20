"""job_postings, jd_requirements.

docs/layer-rules.md 1절 / task-02
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, check_in

# Sprint 1 은 Wanted 만 지원한다. 다른 사이트는 unsupported_site 로 막는다.
POSTING_SOURCES = ("wanted",)
POSTING_PARSE_STATUSES = ("succeeded", "partial", "failed")
DOMAIN_CATEGORIES = ("finance", "game", "travel", "shopping", "medical", "mobility", "etc")

# ⚠ 미합의: docs/db-schema.md 는 required/preferred/unknown,
#   spec/shared/contracts/openapi.yaml 의 JdCategory 는 required/preferred/responsibility 다.
#   spec/shared/contracts/migration.md 에 기록이 없어 임의로 한쪽을 고르지 않고 합집합으로 둔다.
#   팀 결정 전까지 BE 는 API 에 `unknown` 을 내보내지 않는다.
JD_CATEGORIES = ("required", "preferred", "responsibility", "unknown")


class JobPosting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Wanted 공고. normalized URL 기준으로 행을 재사용한다 (fetched_at TTL 24시간)."""

    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("normalized_url", name="uq_job_postings_normalized_url"),
        CheckConstraint(check_in("source", POSTING_SOURCES), name="job_postings_source"),
        CheckConstraint(
            check_in("parse_status", POSTING_PARSE_STATUSES), name="job_postings_parse_status"
        ),
        CheckConstraint(
            check_in("domain_category", DOMAIN_CATEGORIES) + " OR domain_category IS NULL",
            name="job_postings_domain_category",
        ),
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="wanted")
    # Wanted 공고 번호. 같은 공고의 URL 변형을 대조할 때 쓴다.
    source_posting_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)

    position: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # domain_lead 페르소나의 question frame 선택 기준이 된다.
    domain_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # tech_tags 의 원천 (docs/db-schema.md Wanted 공고 절)
    skill_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")

    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False)
    parse_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 재사용 판정 기준 시각. 24시간 이내 성공본이면 다시 가져오지 않는다.
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JdRequirement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """공고에서 뽑은 요구사항 한 줄. 최대 20개 (JD_REQUIREMENT_LIMIT)."""

    __tablename__ = "jd_requirements"
    __table_args__ = (
        UniqueConstraint(
            "job_posting_id", "display_order", name="uq_jd_requirements_posting_order"
        ),
        CheckConstraint(check_in("category", JD_CATEGORIES), name="jd_requirements_category"),
        Index("ix_jd_requirements_job_posting_id", "job_posting_id"),
    )

    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    tech_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
