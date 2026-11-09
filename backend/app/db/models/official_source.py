"""사용자·면접과 독립적인 append-only 공식 원문 snapshot."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class OfficialSourceSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "official_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "catalog_key",
            "catalog_hash",
            "page_content_hash",
            "retrieved_at",
            name="uq_official_snapshot",
        ),
        CheckConstraint("start_line > 0 AND end_line >= start_line", name="line_range"),
        CheckConstraint(
            "char_length(content_hash) = 64 AND char_length(page_content_hash) = 64 "
            "AND char_length(catalog_hash) = 64",
            name="hashes",
        ),
        Index("ix_official_snapshot_catalog_retrieved", "catalog_key", "retrieved_at"),
    )

    catalog_key: Mapped[str] = mapped_column(String(100), nullable=False)
    catalog_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    technology: Mapped[str] = mapped_column(String(100), nullable=False)
    technology_version: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_heading: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_content: Mapped[str] = mapped_column(Text, nullable=False)
    page_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
