"""job_postings, jd_requirements.

docs/layer-rules.md 1절 / task-02

Sprint 1 은 Wanted 만 지원한다. normalized_url 기준으로 행을 재사용하고,
fetched_at 이 TTL(기본 24시간) 이내인 success 행이면 재수집하지 않는다.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobPosting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """수집한 채용 공고 1건. site_adapter 는 어댑터별 성공률 비교 축이라 항상 기록한다."""

    __tablename__ = "job_postings"
    __table_args__ = (
        CheckConstraint("parse_status IN ('success','failed')", name="job_postings_parse_status"),
        CheckConstraint("content_form IN ('text','image')", name="job_postings_content_form"),
    )

    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    site_adapter: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(300))
    company_name: Mapped[str | None] = mapped_column(String(300))
    content_form: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'text'")
    )
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_image_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    skill_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False)
    parse_error_code: Mapped[str | None] = mapped_column(String(50))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JdRequirement(Base, UUIDPrimaryKeyMixin):
    """공고에서 뽑은 요구사항 1줄. Wanted 구조화 필드를 우선 신뢰한다."""

    __tablename__ = "jd_requirements"
    __table_args__ = (
        CheckConstraint(
            "requirement_type IN ('required','preferred','unknown')",
            name="jd_requirements_type",
        ),
        Index("ix_jd_requirements_posting_order", "job_posting_id", "display_order"),
    )

    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    tech_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
