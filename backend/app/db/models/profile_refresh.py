"""보고서 성공과 같은 트랜잭션에서 보존하는 프로필 갱신 전달 기록."""

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, check_in


class ProfileRefreshRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "profile_refresh_requests"
    __table_args__ = (
        UniqueConstraint("report_id", "report_revision", name="uq_profile_refresh_report_revision"),
        CheckConstraint(
            check_in("status", ("pending", "queued", "running", "succeeded", "failed")),
            name="status",
        ),
        CheckConstraint("report_revision >= 1", name="revision"),
        CheckConstraint("dispatch_attempts >= 0 AND dispatch_attempts <= 5", name="attempts"),
        Index("ix_profile_refresh_due", "status", "next_attempt_at", "id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_reports.id", ondelete="CASCADE")
    )
    report_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    dispatch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_error: Mapped[str | None] = mapped_column(Text)
