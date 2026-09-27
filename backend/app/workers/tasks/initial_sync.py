"""M1 큐 태스크. auth service 가 연동 직후 enqueue 한다.
pipeline/initial_sync.py 를 호출하는 얇은 껍데기.

확정본 §2 M1 / task-08

★ GithubClient 생성(토큰 복호화)은 task-06 core/crypto.py 가 아직 골격이라 여기서
  완성하지 않는다. `_build_github_client` 가 그 연결 지점이며, task-06 이 develop 에
  머지되면 `core.crypto.decrypt_token` 을 호출하도록 채운다. 그 전까지 이 태스크는
  ARQ WorkerSettings 에 등록해도 실행 시 NotImplementedError 로 실패한다 — 등록(task-11)
  자체는 막지 않는다.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import GithubAccount
from app.features.analysis.pipeline.initial_sync import run_initial_sync
from app.integrations.github.client import GithubClient


async def _build_github_client(session: AsyncSession, github_account_id: uuid.UUID) -> GithubClient:
    """github_accounts 의 암호화 토큰을 복호화해 GithubClient 를 만든다.

    입력: DB session, github_accounts.id. 출력: GithubClient.
    task-06 의 core/crypto.decrypt_token 이 아직 없어 여기서 막힌다(PENDING_TEAM).
    """
    account = await session.get(GithubAccount, github_account_id)
    if account is None:
        raise ValueError(f"github_account not found: {github_account_id}")
    raise NotImplementedError(
        "core.crypto.decrypt_token 이 필요하다 (task-06 머지 후 연결, backend/docs/task-06-auth.md)"
    )


async def initial_sync(ctx: dict[str, Any], user_id: str, github_account_id: str) -> int:
    """ARQ job 진입점. 입력: ARQ ctx, user_id, github_account_id(문자열 UUID). 출력: 수집한 repo 수.

    session 은 ctx["db_session_factory"] 로 주입받는다 — arq_app.py(task-11) 가 WorkerSettings.
    on_startup 에서 채운다.
    """
    session_factory = ctx["db_session_factory"]
    async with session_factory() as session, session.begin():
        client = await _build_github_client(session, uuid.UUID(github_account_id))
        return await run_initial_sync(
            session,
            user_id=uuid.UUID(user_id),
            github_account_id=uuid.UUID(github_account_id),
            client=client,
        )
