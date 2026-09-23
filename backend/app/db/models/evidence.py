"""evidences, turn_evidences, evidence_conflicts.

★ evidences.git_ref 는 NOT NULL — 없으면 재조회가 불가능하다.
★ evidences.tool_name NULL = L2 사전분석 부산물, 값 있음 = 면접 중 Tool 호출.
★ evidence_conflicts 는 1차에 테이블만 만들고 행을 만들지 않는다. 미리 만드는 이유는
  FK 가 document_claims · evidences 양쪽을 참조해서, 나중에 추가하면 그 시점의
  정합성을 다시 봐야 하기 때문이다.

docs/db-schema.md / task-02
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, check_in

# Sprint 1 Evidence Retriever 범위. 전체 tree scan·전역 검색·private repo 는 제외다.
EVIDENCE_SOURCE_TYPES = ("readme", "repo_metadata", "languages", "commit", "file")
# question_basis: 질문 생성 근거 / evaluation_basis: 답변 평가·리포트·conflict 판정 근거
EVIDENCE_USAGES = ("question_basis", "evaluation_basis")
# Sprint 1 은 answer_vs_code 만 쓴다.
CONFLICT_SOURCES = ("answer_vs_code",)
# resolution 은 Sprint 2. Sprint 1 은 unresolved 로만 남긴다.
CONFLICT_VERDICTS = ("unresolved",)


class Evidence(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """근거 스냅샷. evidenceCheck 가 화면에 뜬 순간 이 행이 있어야 한다."""

    __tablename__ = "evidences"
    __table_args__ = (
        CheckConstraint(check_in("source_type", EVIDENCE_SOURCE_TYPES), name="evidences_source"),
        Index("ix_evidences_session_id", "interview_session_id"),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # commit SHA 또는 branch. 이게 없으면 나중에 같은 내용을 다시 꺼낼 수 없다.
    git_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL 이면 L2 사전분석 부산물, 값이 있으면 면접 중 Tool 호출로 가져온 근거.
    tool_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retrieved_for_turn: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class TurnEvidence(Base, CreatedAtMixin):
    """턴과 근거의 연결. PK 에 usage 가 들어간다 —
    같은 evidence 가 질문 근거이면서 채점 근거일 수 있다.

    ⚠ 이 INSERT 누락이 가장 조용한 버그다. 화면은 정상으로 보이고 Eval 만 깨진다.
      질문 INSERT 와 같은 트랜잭션으로 묶는다 (features/interview/turn_service.py).
    """

    __tablename__ = "turn_evidences"
    __table_args__ = (
        CheckConstraint(check_in("usage", EVIDENCE_USAGES), name="turn_evidences_usage"),
    )

    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_turns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidences.id", ondelete="CASCADE"),
        primary_key=True,
    )
    usage: Mapped[str] = mapped_column(String(20), primary_key=True)


class EvidenceConflict(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """답변과 코드의 불일치. Sprint 1 은 테이블만 만들고 행을 만들지 않는다."""

    __tablename__ = "evidence_conflicts"
    __table_args__ = (
        CheckConstraint(check_in("source", CONFLICT_SOURCES), name="evidence_conflicts_source"),
        CheckConstraint(check_in("verdict", CONFLICT_VERDICTS), name="evidence_conflicts_verdict"),
        Index("ix_evidence_conflicts_turn_id", "turn_id"),
    )

    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidences.id", ondelete="CASCADE"), nullable=False
    )
    # ⚠ FK 를 걸지 않는다. Sprint 2 에서 document_claims FK 를 추가한다.
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    source: Mapped[str] = mapped_column(String(30), nullable=False, server_default="answer_vs_code")
    # 사용자 답변에서 추출한 주장 원문
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 충돌 판정에 쓴 근거 스냅샷
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unresolved")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
