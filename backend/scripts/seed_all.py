"""시드 5개를 순서대로 실행. README 의 'uv run python -m scripts.seed_all' 진입점.

README.md / task-03

★ prompt_versions 는 seed_prompt_versions.seed_prompt_versions() 가 이미 구현돼 있지만
  일곱 task 전부의 검수된 prompt 본문(PromptSpec)이 있어야 호출할 수 있다. 현재
  ai/prompts/ 에는 director_v1 하나만 있고 나머지 여섯(repo_shallow_v1 등)은 AI 팀의
  프롬프트 검수 대기 중이라 여기서 호출하지 않는다. 전부 갖춰지면 이 파일에서
  PromptSpec 목록을 조립해 seed_prompt_versions 를 추가한다.
  persona / topic_taxonomy / probe_pattern 은 Sprint 1 DB 에서 제외돼 시드하지 않는다
  (backend/CLAUDE.md 고정 구현 기준).
"""

import asyncio

from app.db.session import dispose_engine, get_session_factory
from scripts.seed_domain_question_frames import seed_domain_question_frames
from scripts.seed_score_criteria import seed_score_criteria


async def seed_all() -> None:
    """도메인 지식 시드 전체를 한 transaction 에서 실행하고 commit 한다."""
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await seed_score_criteria(session)
        await seed_domain_question_frames(session)


async def _main() -> None:
    try:
        await seed_all()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
