"""품질 지표 읽기 전용 쿼리. API 로 노출하지 않고 운영 점검·Eval 에서 호출한다.

기간 필터는 since(포함) / until(미포함) 이며 둘 다 None 이면 전체 기간이다.
데이터가 없어 정의할 수 없는 값은 0 이 아니라 None 으로 돌려준다.

docs/layer-rules.md 1절 / task-17
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    Evidence,
    InterviewTurn,
    Repository,
    SessionRepository,
    TurnEvidence,
)

AI_REMOVED = "ai_removed"
REPORT_VIEWED = "report_viewed"


@dataclass(frozen=True)
class ToolUsage:
    """evidence tool 사용 비율. ratio 는 분모(turns_with_evidence)가 0 이면 None."""

    turns_with_evidence: int
    turns_with_tool: int

    @property
    def ratio(self) -> float | None:
        if self.turns_with_evidence == 0:
            return None
        return self.turns_with_tool / self.turns_with_evidence


@dataclass(frozen=True)
class AiRemovedRepository:
    interview_session_id: uuid.UUID
    repository_id: uuid.UUID
    full_name: str
    created_at: datetime


async def get_average_depth(
    db: AsyncSession, *, since: datetime | None = None, until: datetime | None = None
) -> float | None:
    """interview_turns.depth 의 평균.

    입력: 턴 생성 시각(created_at) 기간. 출력: 평균 depth, 턴이 없으면 None.
    status(asked/answered)는 가리지 않는다 — 질문이 던져진 턴은 모두 센다.
    """
    stmt = select(func.avg(InterviewTurn.depth))
    if since is not None:
        stmt = stmt.where(InterviewTurn.created_at >= since)
    if until is not None:
        stmt = stmt.where(InterviewTurn.created_at < until)
    average = await db.scalar(stmt)
    return None if average is None else float(average)


async def get_evidence_tool_usage(
    db: AsyncSession, *, since: datetime | None = None, until: datetime | None = None
) -> ToolUsage:
    """근거가 연결된 턴 중 면접 중 Tool 호출 근거를 쓴 턴의 비율.

    분모: turn_evidences 가 1건 이상인 서로 다른 턴 (usage 무관).
    분자: 그 턴 중 evidences.tool_name 이 NULL 이 아닌 근거가 연결된 턴.
    입력: 턴 생성 시각(created_at) 기간.
    """
    stmt = (
        select(
            func.count(func.distinct(TurnEvidence.turn_id)),
            func.count(func.distinct(TurnEvidence.turn_id)).filter(Evidence.tool_name.is_not(None)),
        )
        .join(Evidence, Evidence.id == TurnEvidence.evidence_id)
        .join(InterviewTurn, InterviewTurn.id == TurnEvidence.turn_id)
    )
    if since is not None:
        stmt = stmt.where(InterviewTurn.created_at >= since)
    if until is not None:
        stmt = stmt.where(InterviewTurn.created_at < until)
    total, with_tool = (await db.execute(stmt)).one()
    return ToolUsage(turns_with_evidence=total, turns_with_tool=with_tool)


async def list_ai_removed_repositories(
    db: AsyncSession, *, since: datetime | None = None, until: datetime | None = None
) -> list[AiRemovedRepository]:
    """selection_source='ai_removed' 인 session_repositories 목록, 오래된 순.

    입력: session_repositories 생성 시각(created_at) 기간. 출력: 없으면 빈 리스트.
    """
    stmt = (
        select(
            SessionRepository.interview_session_id,
            SessionRepository.repository_id,
            Repository.full_name,
            SessionRepository.created_at,
        )
        .join(Repository, Repository.id == SessionRepository.repository_id)
        .where(SessionRepository.selection_source == AI_REMOVED)
        .order_by(SessionRepository.created_at, SessionRepository.id)
    )
    if since is not None:
        stmt = stmt.where(SessionRepository.created_at >= since)
    if until is not None:
        stmt = stmt.where(SessionRepository.created_at < until)
    rows = await db.execute(stmt)
    return [AiRemovedRepository(*row) for row in rows.all()]


async def count_report_viewed(
    db: AsyncSession, *, since: datetime | None = None, until: datetime | None = None
) -> int:
    """report_viewed 이벤트 수. 입력: events.created_at 기간. 없으면 0."""
    stmt = select(func.count()).select_from(Event).where(Event.event_name == REPORT_VIEWED)
    if since is not None:
        stmt = stmt.where(Event.created_at >= since)
    if until is not None:
        stmt = stmt.where(Event.created_at < until)
    return await db.scalar(stmt) or 0
