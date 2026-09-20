"""user_documents, document_claims.

★ document_claims 는 1차 포함이다 (설계 초기안의 '1단계 제외' 는 폐기).
  이미 끝난 면접의 '어느 주장이 다뤄졌나' 는 소급 복원이 불가능하다.
  1차 컬럼: claim_text / claim_type / tech_tags / paragraph_no / confidence
  2차 컬럼: topic_code(FK) / repository_hint(FK repositories) ← 대조의 열쇠

docs/db-schema.md / task-02

Sprint 1 은 테이블만 만들고 document_claims row 는 만들지 않는다.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, check_in

# Sprint 1 의 /documents/preview 는 portfolio 만 받는다. 자소서는 Sprint 2.
DOCUMENT_TYPES = ("portfolio", "cover_letter")
# openapi DocumentExtractStatus 와 같은 집합.
DOCUMENT_EXTRACT_STATUSES = ("succeeded", "partial", "failed")


class UserDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """업로드 문서의 추출 결과. 파일 바이너리는 저장하지 않는다."""

    __tablename__ = "user_documents"
    __table_args__ = (
        CheckConstraint(check_in("doc_type", DOCUMENT_TYPES), name="user_documents_doc_type"),
        CheckConstraint(
            check_in("extract_status", DOCUMENT_EXTRACT_STATUSES),
            name="user_documents_extract_status",
        ),
        Index("ix_user_documents_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="portfolio")
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # owner/repo 까지 정규화한 GitHub URL. repo_select 의 portfolio_mentioned 신호가 된다.
    extracted_github_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    extract_status: Mapped[str] = mapped_column(String(20), nullable=False)
    extract_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 길이 초과로 축약했으면 true — extract_status='partial' 의 사유가 된다.
    is_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class DocumentClaim(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """자소서/포트폴리오에서 뽑은 검증 가능한 주장.

    Sprint 1 은 테이블만 만들고 row 를 만들지 않는다. 지금 만들어 두는 이유는
    evidence_conflicts.claim_id 가 나중에 이 테이블을 FK 로 참조하기 때문이다.
    """

    __tablename__ = "document_claims"
    __table_args__ = (Index("ix_document_claims_document_id", "document_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_documents.id", ondelete="CASCADE"), nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 값 집합은 Sprint 2 claim 추출 구현 때 확정한다. 지금 CHECK 를 걸지 않는다.
    claim_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tech_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    paragraph_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
