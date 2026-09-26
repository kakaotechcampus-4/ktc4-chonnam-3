"""users, github_accounts (OAuth 토큰 컬럼 포함 - §1.1).

docs/db-schema.md / task-02

관계(relationship)는 두지 않는다. async 에서 lazy load 는 MissingGreenlet 을 부르고,
읽기는 features/*/queries.py 의 명시적 join 으로 처리한다 (docs/layer-rules.md).
"""

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, check_in

USER_STATUSES = ("active", "suspended", "withdrawn")
# GitHub API 호출 가능 여부 판단용. 만료(expires)는 long-lived token 전제라 두지 않는다.
TOKEN_STATUSES = ("valid", "revoked", "invalid")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """DEVON 사용자. created_at 이 API 의 joinedAt 이다."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            check_in("status", USER_STATUSES),
            name="status",
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # suspended / withdrawn 이면 로그인을 막는다 (features/auth/service.py).
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")


class GithubAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """GitHub 연동 계정. BE 가 GitHub API 를 대행 호출하기 위한 토큰만 저장한다.

    DEVON 자체 JWT 는 여기 저장하지 않는다. token_type / token_expires_at /
    refresh_token_* 은 long-lived OAuth App access token 전제라 만들지 않는다
    (docs/db-schema.md "GitHub Accounts Token Fields").
    """

    __tablename__ = "github_accounts"
    __table_args__ = (
        CheckConstraint(
            check_in("token_status", TOKEN_STATUSES),
            name="token_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 사용자당 GitHub 계정 1개
    )
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    login: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_repo_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ⚠ 평문 저장·응답·로그 노출 금지. core/crypto.py 로 AES-GCM 암호화한 값만 넣는다.
    access_token_encrypted: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    token_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="valid")
    token_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
