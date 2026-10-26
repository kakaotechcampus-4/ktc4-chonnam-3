"""품질 지표 읽기 전용 쿼리. API 로 노출하지 않고 운영 점검·Eval 에서 호출한다.

기간 필터는 since(포함) / until(미포함) 이며 둘 다 None 이면 전체 기간이다.
데이터가 없어 정의할 수 없는 값은 0 이 아니라 None 으로 돌려준다.

docs/layer-rules.md 1절 / task-17
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewTurn


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
