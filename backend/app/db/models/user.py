from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityTimestamps


class User(IdentityTimestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'withdrawn')", name="ck_users_status"),
    )

    display_name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_generation: Mapped[UUID] = mapped_column(
        default=uuid4, server_default=func.gen_random_uuid()
    )


class AuthSession(IdentityTimestamps, Base):
    __tablename__ = "auth_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    generation: Mapped[UUID]
    refresh_jti: Mapped[UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GitHubAccount(IdentityTimestamps, Base):
    __tablename__ = "github_accounts"
    __table_args__ = (
        CheckConstraint(
            "token_status IN ('valid', 'revoked')", name="ck_github_accounts_token_status"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    github_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    login: Mapped[str] = mapped_column(String(255))
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    token_status: Mapped[str] = mapped_column(String(16), default="valid", server_default="valid")
    token_scope: Mapped[str] = mapped_column(String(255))
