"""task-03 시드 대상(prompt version·domain question frame·score criteria) 중
score_criteria 와 domain_question_frames 를 실행한다. prompt_versions 는 아래 ★ 이유로
여기서 넣지 않는다. README 의 'uv run python -m scripts.seed_all' 진입점.

README.md / task-03

★ prompt_versions 초기 seed(seed_prompt_versions.seed_prompt_versions)는 고정 일곱
  task 의 검수된 prompt 본문(PromptSpec)이 모두 있어야 호출할 수 있다. 검수 본문이
  없는 task 가 남아 있어 여기서 호출하지 않는다. 검수를 마친 task 는
  scripts.register_prompt 로 환경별 DB 에 등록한다
  (backend/docs/llm-connection.md 의 '앱에서 사용할 프롬프트 등록').
  persona / topic_taxonomy / probe_pattern 은 Sprint 1 DB 에서 제외돼 시드하지 않는다
  (backend/CLAUDE.md 고정 구현 기준).
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from scripts.seed_domain_question_frames import seed_domain_question_frames
from scripts.seed_score_criteria import seed_score_criteria


async def seed_all(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """도메인 지식 시드 전체를 한 transaction 에서 실행하고 commit 한다."""
    async with session_factory() as session, session.begin():
        await seed_score_criteria(session)
        await seed_domain_question_frames(session)


async def _main() -> None:
    # 엔진은 앱 lifespan 이 소유한다 (app/db/session.py). 스크립트는 직접 만들고 닫는다.
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        await seed_all(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
