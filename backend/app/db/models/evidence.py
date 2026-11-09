"""evidences, turn_evidences, evidence_conflicts.

★ evidences.git_ref 는 NOT NULL — 없으면 재조회가 불가능하다.
★ evidences.tool_name NULL = L2 사전분석 부산물, 값 있음 = 면접 중 Tool 호출.
★ evidence_conflicts 는 1차에 테이블만 만들고 행을 만들지 않는다. 미리 만드는 이유는
  FK 가 document_claims · evidences 양쪽을 참조해서, 나중에 추가하면 그 시점의
  정합성을 다시 봐야 하기 때문이다.

docs/db-schema.md / task-02
"""

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
        CheckConstraint(check_in("source_type", EVIDENCE_SOURCE_TYPES), name="source"),
        CheckConstraint(
            "(start_line IS NULL AND end_line IS NULL) OR "
            "(start_line IS NOT NULL AND end_line IS NOT NULL "
            "AND start_line > 0 AND end_line >= start_line "
            "AND path IS NOT NULL AND metadata_key IS NULL)",
            name="line_range",
        ),
        Index("ix_evidences_session_id", "interview_session_id"),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # commit SHA. 이게 없으면 나중에 같은 내용을 다시 꺼낼 수 없다.
    git_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 실제 파일 위치가 있는 경우에만 쌍으로 저장한다. metadata에는 줄 번호가 없다.
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    __table_args__ = (CheckConstraint(check_in("usage", EVIDENCE_USAGES), name="usage"),)

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
        CheckConstraint(check_in("source", CONFLICT_SOURCES), name="source"),
        CheckConstraint(check_in("verdict", CONFLICT_VERDICTS), name="verdict"),
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


class DocumentClaimComparison(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """문서와 코드의 기술적 대조. 첫 질문 전에도 결과·미확인 사유를 보존한다."""

    __tablename__ = "document_claim_comparisons"
    __table_args__ = (
        CheckConstraint(
            check_in("status", ("consistent", "conflicting", "unverified")), name="status"
        ),
        CheckConstraint(
            check_in(
                "execution_status", ("succeeded", "failed", "not_available", "budget_exhausted")
            ),
            name="execution_status",
        ),
        UniqueConstraint("run_id", "claim_id", name="uq_claim_comparison_run_claim"),
        Index("ix_claim_comparisons_interview", "interview_session_id"),
    )

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_claims.id", ondelete="CASCADE"), nullable=False
    )
    # 같은 입력의 실패 후 명시 재준비도 새 실행으로 남겨 과거 인용을 바꾸지 않는다.
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # 원문은 evidences에 보존한다. 위치·버전·해시를 함께 저장해 인용을 재검증한다.
    code_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
