"""users, github_accounts (OAuth 토큰 컬럼 포함 - §1.1).

docs/db-schema.md / task-02
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """DEVON 사용자. GitHub 계정 정보는 github_accounts 에 둔다."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','withdrawn')",
            name="users_status",
        ),
    )

    login: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class GithubAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """GitHub API 대행 호출용 토큰 보관. 평문 저장·응답·log 노출 금지.

    token_type / token_expires_at / refresh_token_* 는 만들지 않는다
    (long-lived OAuth App access token 전제, docs/db-schema.md).
    """

    __tablename__ = "github_accounts"
    __table_args__ = (
        CheckConstraint("token_status IN ('valid','revoked')", name="github_accounts_token_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    login: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'valid'")
    )
    token_scope: Mapped[str | None] = mapped_column(String(200))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
