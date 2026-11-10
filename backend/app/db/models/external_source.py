"""코드 Evidence와 구분한 면접별 외부 원문. 검색 자료는 개인 기여의 증거가 아니다."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class InterviewExternalSource(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_external_sources"
    __table_args__ = (
        UniqueConstraint("interview_session_id", "url", "content_hash", name="uq_external_source"),
        CheckConstraint(
            "content_scope IN ('search_snippet', 'extracted_page')", name="content_scope"
        ),
        Index("ix_external_sources_interview", "interview_session_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # 공통 원문은 별도로 보존하며 면접별 소유권·원문 재생 경로는 기존 표에 유지한다.
    official_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "official_source_snapshots.id",
            name="fk_external_source_official_snapshot",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
