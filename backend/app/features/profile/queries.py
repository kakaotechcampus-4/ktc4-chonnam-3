"""profile_summary 용 DB 조회·저장. 집계 규칙은 llm_tasks/profile_summary.py 에 있다. task-16"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewTurn, RepoAnalysis, Repository, UserProfileSummary
from app.db.models.interview import InterviewSession, SessionRepository

SHALLOW_USABLE_STATUSES = ("succeeded", "partial")


async def completed_interview_repositories(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[Repository]:
    """completed 면접에 쓰인 저장소를 repo id 로 중복 제거해 id 순으로 돌려준다."""
    rows = await db.scalars(
        select(Repository)
        .join(SessionRepository, SessionRepository.repository_id == Repository.id)
        .join(InterviewSession, InterviewSession.id == SessionRepository.interview_session_id)
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.status == "completed",
            Repository.user_id == user_id,
        )
        .distinct()
        .order_by(Repository.id)
    )
    return list(rows)


async def shallow_results(
    db: AsyncSession, *, repo_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, object]]:
    """저장소별 가장 최근 L1 결과(JSON). 없는 저장소는 키가 없다."""
    if not repo_ids:
        return {}
    rows = await db.execute(
        select(RepoAnalysis.repository_id, RepoAnalysis.result)
        .where(
            RepoAnalysis.repository_id.in_(repo_ids),
            RepoAnalysis.analysis_level == "l1",
            RepoAnalysis.status.in_(SHALLOW_USABLE_STATUSES),
        )
        .order_by(RepoAnalysis.created_at.desc(), RepoAnalysis.id.desc())
    )
    found: dict[uuid.UUID, dict[str, object]] = {}
    for repo_id, result in rows:
        if isinstance(result, dict):
            found.setdefault(repo_id, result)
    return found


async def answered_turns(
    db: AsyncSession, *, user_id: uuid.UUID, repo_ids: list[uuid.UUID], limit: int
) -> list[tuple[uuid.UUID, InterviewTurn]]:
    """대상 저장소를 쓴 completed 면접의 답변 완료 턴. 최근 면접·낮은 turn_no 순."""
    if not repo_ids:
        return []
    used = (
        select(SessionRepository.interview_session_id)
        .where(SessionRepository.repository_id.in_(repo_ids))
        .scalar_subquery()
    )
    rows = await db.execute(
        select(InterviewSession.id, InterviewTurn)
        .join(InterviewTurn, InterviewTurn.interview_session_id == InterviewSession.id)
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.status == "completed",
            InterviewSession.id.in_(used),
            InterviewTurn.status == "answered",
            InterviewTurn.answer_text.is_not(None),
        )
        .order_by(
            InterviewSession.completed_at.desc().nulls_last(),
            InterviewSession.id,
            InterviewTurn.turn_no,
        )
        .limit(limit)
    )
    return [(interview_id, turn) for interview_id, turn in rows]


async def interview_repository_names(
    db: AsyncSession, *, interview_ids: list[uuid.UUID], repo_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not interview_ids:
        return {}
    rows = await db.execute(
        select(SessionRepository.interview_session_id, Repository.name)
        .join(Repository, Repository.id == SessionRepository.repository_id)
        .where(
            SessionRepository.interview_session_id.in_(interview_ids),
            Repository.id.in_(repo_ids),
        )
        .order_by(SessionRepository.display_order, Repository.name)
    )
    names: dict[uuid.UUID, list[str]] = {}
    for interview_id, name in rows:
        names.setdefault(interview_id, []).append(name)
    return names


async def get_summary(db: AsyncSession, *, user_id: uuid.UUID) -> UserProfileSummary | None:
    summary: UserProfileSummary | None = await db.scalar(
        select(UserProfileSummary).where(UserProfileSummary.user_id == user_id)
    )
    return summary


async def save_summary(
    db: AsyncSession, *, user_id: uuid.UUID, values: dict[str, object], generated_at: datetime
) -> None:
    """사용자당 한 행. 이미 있으면 같은 행을 갱신한다. 호출자의 transaction 안에서 실행한다."""
    stmt = insert(UserProfileSummary).values(user_id=user_id, generated_at=generated_at, **values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[UserProfileSummary.user_id],
            set_={**values, "generated_at": generated_at, "updated_at": func.now()},
        )
    )
