"""initial_sync M1 — token_invalid 시 github_accounts.token_status 갱신 (task-08).

upsert 자체의 정확성(ON CONFLICT DO UPDATE)은 실제 PostgreSQL 제약이 있어야 검증되므로
tests/features/test_initial_sync_postgres.py 에 별도로 둔다(TEST_POSTGRES_URL 필요).
"""

from unittest import mock
from uuid import uuid4

import pytest

from app.features.analysis.pipeline.initial_sync import run_initial_sync
from app.integrations.github.base import GITHUB_ERROR_TOKEN_INVALID, GithubApiError
from app.integrations.github.client import GithubClient


def _session() -> mock.AsyncMock:
    session = mock.AsyncMock()
    session.execute = mock.AsyncMock()
    return session


async def test_token_invalid_marks_account_revoked_and_reraises() -> None:
    session = _session()
    client = mock.create_autospec(GithubClient, instance=True)
    client.list_repositories = mock.AsyncMock(
        side_effect=GithubApiError(GITHUB_ERROR_TOKEN_INVALID, status_code=401)
    )
    github_account_id = uuid4()

    with pytest.raises(GithubApiError) as caught:
        await run_initial_sync(
            session, user_id=uuid4(), github_account_id=github_account_id, client=client
        )

    assert caught.value.error_code == GITHUB_ERROR_TOKEN_INVALID
    session.execute.assert_awaited_once()
    executed_statement = session.execute.await_args.args[0]
    compiled = executed_statement.compile(compile_kwargs={"literal_binds": True})
    assert "token_status" in str(compiled)
    assert github_account_id.hex in str(compiled)


async def test_other_github_errors_do_not_touch_token_status() -> None:
    session = _session()
    client = mock.create_autospec(GithubClient, instance=True)
    client.list_repositories = mock.AsyncMock(
        side_effect=GithubApiError("repo_unreachable", status_code=500)
    )

    with pytest.raises(GithubApiError):
        await run_initial_sync(session, user_id=uuid4(), github_account_id=uuid4(), client=client)

    session.execute.assert_not_awaited()


async def test_upserts_one_row_per_returned_repo() -> None:
    from app.integrations.github.base import RepoSummary

    session = _session()
    client = mock.create_autospec(GithubClient, instance=True)
    client.list_repositories = mock.AsyncMock(
        return_value=[
            RepoSummary(github_repo_id=1, name="a", full_name="user/a"),
            RepoSummary(github_repo_id=2, name="b", full_name="user/b"),
        ]
    )

    count = await run_initial_sync(
        session, user_id=uuid4(), github_account_id=uuid4(), client=client
    )

    assert count == 2
    assert session.execute.await_count == 2
