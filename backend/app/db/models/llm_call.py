"""면접의 모델 호출 기록. 질문 생성 전 실패도 원문과 함께 보존한다."""

import uuid

from sqlalchemy import ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class LLMCallRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """호출자가 발급한 id로 저장 재시도를 구분하며 작업 실행을 관리하지 않는다."""

    __tablename__ = "llm_call_records"
    __table_args__ = (
        Index(
            "ix_llm_call_records_interview_session_id_created_at",
            "interview_session_id",
            "created_at",
        ),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_turns.id", ondelete="SET NULL"), nullable=True
    )
    turn_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    # 실제 호출 없는 예산 실패는 빈 배열이며, 미확인 token 수는 JSON null을 유지한다.
    attempts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    failure: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # 모델 성공 이후 상태 변경으로 적용하지 못한 결과를 모델 실패로 바꾸지 않는다.
    discard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
