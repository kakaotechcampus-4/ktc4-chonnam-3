"""리포트 / 점수 / 페르소나 피드백 읽기 쿼리.

docs/layer-rules.md 1절 / task-16
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    ReportDisagreement,
    ReportScore,
    Repository,
    ScoreCriterion,
    SessionRepository,
)


async def get_owned_interview(
    db: AsyncSession, *, user_id: uuid.UUID, interview_id: uuid.UUID
) -> tuple[InterviewSession, JobPosting] | None:
    """본인 면접과 그 공고. 입력: 사용자 id, interviewId. 출력: 없거나 남의 것이면 None."""
    row = (
        await db.execute(
            select(InterviewSession, JobPosting)
            .join(JobPosting, JobPosting.id == InterviewSession.job_posting_id)
            .where(InterviewSession.id == interview_id, InterviewSession.user_id == user_id)
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def get_report(db: AsyncSession, *, interview_id: uuid.UUID) -> InterviewReport | None:
    """면접의 리포트. 입력: interviewId. 출력: 아직 생성 전이면 None."""
    report: InterviewReport | None = await db.scalar(
        select(InterviewReport).where(InterviewReport.interview_session_id == interview_id)
    )
    return report


async def count_answered_turns(db: AsyncSession, *, interview_id: uuid.UUID) -> int:
    """답변 완료(status='answered') 턴 수. 리포트 생성 가능 조건에 쓴다."""
    count = await db.scalar(
        select(func.count())
        .select_from(InterviewTurn)
        .where(
            InterviewTurn.interview_session_id == interview_id,
            InterviewTurn.status == "answered",
        )
    )
    return int(count or 0)


async def list_scores(db: AsyncSession, *, report_id: uuid.UUID) -> list[tuple[str, str, float]]:
    """항목별 점수. 출력: (score_key, label_ko, score) 를 score_criteria.display_order 순으로."""
    rows = await db.execute(
        select(ReportScore.score_key, ScoreCriterion.label_ko, ReportScore.score)
        .join(ScoreCriterion, ScoreCriterion.score_key == ReportScore.score_key)
        .where(ReportScore.report_id == report_id)
        .order_by(ScoreCriterion.display_order)
    )
    return [(key, label, float(score)) for key, label, score in rows]


async def list_disagreed_personas(db: AsyncSession, *, report_id: uuid.UUID) -> set[str]:
    """이의를 제출한 persona 집합. Sprint 1 은 row 를 만들지 않아 보통 비어 있다."""
    rows = await db.scalars(
        select(ReportDisagreement.persona).where(ReportDisagreement.report_id == report_id)
    )
    return set(rows)


async def list_turns(db: AsyncSession, *, interview_id: uuid.UUID) -> list[InterviewTurn]:
    """면접의 턴을 turn_no 순으로. 입력: interviewId. 출력: 턴 목록."""
    rows = await db.scalars(
        select(InterviewTurn)
        .where(InterviewTurn.interview_session_id == interview_id)
        .order_by(InterviewTurn.turn_no)
    )
    return list(rows)


async def list_repository_names(db: AsyncSession, *, interview_id: uuid.UUID) -> list[str]:
    """선택 repo 이름. 출력 순서 = 선택 순서(display_order)."""
    rows = await db.scalars(
        select(Repository.name)
        .join(SessionRepository, SessionRepository.repository_id == Repository.id)
        .where(SessionRepository.interview_session_id == interview_id)
        .order_by(SessionRepository.display_order)
    )
    return list(rows)
