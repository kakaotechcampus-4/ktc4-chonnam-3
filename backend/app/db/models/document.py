"""user_documents, document_claims.

document_claims 는 Sprint 1 에 테이블만 만들고 row 생성/claim 추출은 하지 않는다
(docs/db-schema.md · backend/CLAUDE.md). 이번 범위(공고 입력 · 레포 목록 · 진행률)에서는
user_documents 만 사용한다 — POST /documents/preview 는 task-09 범위다.

docs/db-schema.md / task-02
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """자소서/포트폴리오 preview 결과. 파일 바이너리는 저장하지 않는다."""

    __tablename__ = "user_documents"
    __table_args__ = (
        CheckConstraint(
            "extract_status IN ('succeeded','partial','failed')",
            name="user_documents_extract_status",
        ),
        Index("ix_user_documents_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    extract_status: Mapped[str] = mapped_column(String(20), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_github_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    failure_reason: Mapped[str | None] = mapped_column(String(50))
