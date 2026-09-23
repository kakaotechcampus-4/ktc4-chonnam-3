"""Public repository collection and its persisted background-job lifecycle."""

import importlib

import httpx
import pytest
from sqlalchemy import select

from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository
from app.db.models.user import GithubAccount, User


async def test_listing_ignores_private_repositories_and_follows_github_pages():
    module = importlib.import_module("app.integrations.github.client")
    assert hasattr(module, "GithubClient"), "GitHub listing client must be implemented"
    seen = []

    def provider(request):
        seen.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200, json=[{"id": 3, "name": "second", "full_name": "dev/second", "private": False}]
            )
        return httpx.Response(
            200,
            json=[
                {"id": 1, "name": "public", "full_name": "dev/public", "private": False},
                {"id": 2, "name": "secret", "full_name": "dev/secret", "private": True},
            ],
            headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        repos = await module.GithubClient("private-test-token", client=http).list_repositories()
    assert [repo.github_repo_id for repo in repos] == [1, 3]
    assert seen[0].url.params["visibility"] == "public"
    assert seen[0].url.params["affiliation"] == "owner"


async def test_listing_refuses_pagination_that_would_leak_provider_token():
    module = importlib.import_module("app.integrations.github.client")
    assert hasattr(module, "GithubClient"), "GitHub listing client must be implemented"
    destinations = []

    def provider(request):
        destinations.append(request.url.host)
        return httpx.Response(
            200, json=[], headers={"link": '<https://attacker.invalid/steal>; rel="next"'}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        with pytest.raises(module.GithubApiError):
            await module.GithubClient("private-test-token", client=http).list_repositories()
    assert destinations == ["api.github.com"]


async def test_listing_deduplicates_repositories_moving_between_pages():
    from app.integrations.github.client import GithubClient

    def provider(request):
        headers = (
            {}
            if request.url.params.get("page") == "2"
            else {
                "link": '<https://api.github.com/user/repos?page=2>; rel="next"',
            }
        )
        return httpx.Response(
            200,
            json=[
                {"id": 1, "name": "repo", "full_name": "user/repo", "private": False},
            ],
            headers=headers,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        repos = await GithubClient("test-token", client=http).list_repositories()
    assert [repo.github_repo_id for repo in repos] == [1]


@pytest.fixture
async def sync_account(db, app):
    user = User(name="Sync member")
    db.add(user)
    await db.flush()
    account = GithubAccount(
        user_id=user.id,
        github_user_id=99,
        login="sync-member",
        access_token_encrypted=app.state.cipher.encrypt("sync-token"),
        token_status="valid",
        token_scope="read:user",
    )
    db.add(account)
    await db.commit()
    return account


async def test_enqueue_is_idempotent_and_has_no_token_in_job_arguments(db, redis, sync_account):
    from arq.jobs import Job

    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

    first = await enqueue_initial_sync(db, redis, sync_account.user_id)
    second = await enqueue_initial_sync(db, redis, sync_account.user_id)
    assert first == second
    job = await db.get(AnalysisJob, first)
    assert job.status == "queued"
    info = await Job(f"initial_sync:{first}", redis).info()
    assert info is not None
    assert info.args == (str(first),)
    assert "sync-token" not in repr(info)


async def test_relogin_restores_lost_queued_job_once(db, redis, app, sync_account):
    import asyncio

    from arq.jobs import Job, JobStatus

    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

    job_id = await enqueue_initial_sync(db, redis, sync_account.user_id)
    await redis.delete(f"arq:job:initial_sync:{job_id}")
    await redis.zrem("arq:queue", f"initial_sync:{job_id}")

    async def relogin():
        async with app.state.session_factory() as session:
            return await enqueue_initial_sync(session, redis, sync_account.user_id)

    assert await asyncio.gather(relogin(), relogin()) == [job_id, job_id]
    job = Job(f"initial_sync:{job_id}", redis)
    assert await job.status() == JobStatus.queued
    assert (await job.info()).args == (str(job_id),)
    assert await redis.zcard("arq:queue") == 1
    assert (await db.get(AnalysisJob, job_id)).status == "queued"


async def test_finished_arq_job_cannot_leave_sql_queued_forever(db, redis, sync_account):
    from arq.jobs import Job, JobStatus
    from arq.worker import Worker

    from app.core.errors import AppError, Reason
    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync
    from app.workers.tasks.initial_sync import initial_sync

    job_id = await enqueue_initial_sync(db, redis, sync_account.user_id)
    # ARQ can fail before the function starts (expired/invalid job or retry limit).
    worker = Worker([initial_sync], redis_pool=redis, burst=True, max_tries=0, handle_signals=False)
    await worker.async_run()
    assert await Job(f"initial_sync:{job_id}", redis).status() == JobStatus.complete
    with pytest.raises(AppError) as error:
        await enqueue_initial_sync(db, redis, sync_account.user_id)
    assert error.value.reason == Reason.INTERNAL_ERROR
    assert (await db.get(AnalysisJob, job_id)).status == "failed"
    next_id = await enqueue_initial_sync(db, redis, sync_account.user_id)
    assert next_id != job_id
    assert await Job(f"initial_sync:{next_id}", redis).status() == JobStatus.queued


async def test_relogin_does_not_restart_running_job_after_queue_loss(db, redis, sync_account):
    from arq.jobs import Job, JobStatus

    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="running")
    db.add(job)
    await db.commit()
    assert await enqueue_initial_sync(db, redis, sync_account.user_id) == job.id
    assert await Job(f"initial_sync:{job.id}", redis).status() == JobStatus.not_found
    await db.refresh(job)
    assert job.status == "running"


async def test_sync_persists_public_metadata_and_finishes_job(db, app, sync_account):
    from app.features.analysis.pipeline.initial_sync import run_initial_sync

    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add(job)
    await db.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=[
                    {
                        "id": 11,
                        "name": "visible",
                        "full_name": "user/visible",
                        "private": False,
                        "language": "Python",
                    },
                    {"id": 12, "name": "secret", "full_name": "user/secret", "private": True},
                ],
            )
        )
    ) as http:
        await run_initial_sync(db, job.id, http, app.state.cipher)
    await db.refresh(job)
    assert job.status == "succeeded"
    repos = (await db.scalars(select(Repository))).all()
    assert [repo.github_repo_id for repo in repos] == [11]
    assert repos[0].primary_language == "Python"
    await db.refresh(sync_account)
    assert sync_account.public_repo_count == 1


async def test_provider_401_revokes_only_the_token_used_by_that_request(db, app, sync_account):
    from app.features.analysis.pipeline.initial_sync import run_initial_sync

    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add(job)
    await db.commit()

    async def provider(request):
        from sqlalchemy import update

        async with app.state.session_factory() as concurrent:
            await concurrent.execute(
                update(GithubAccount)
                .where(GithubAccount.id == sync_account.id)
                .values(access_token_encrypted=app.state.cipher.encrypt("new-token"))
            )
            await concurrent.commit()
        return httpx.Response(401, json={"message": "Bad credentials"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await run_initial_sync(db, job.id, http, app.state.cipher)
    await db.refresh(sync_account)
    await db.refresh(job)
    assert sync_account.token_status == "valid"
    assert app.state.cipher.decrypt(sync_account.access_token_encrypted) == "new-token"
    assert job.status == "failed"
    assert job.error_code == "token_invalid"


async def test_reconnect_during_sync_uses_new_token_after_old_request_fails(
    db, app, redis, sync_account
):
    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync, run_initial_sync
    from app.features.auth.oauth import GitHubProfile, OAuthToken
    from app.features.auth.service import upsert_github_user

    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add(job)
    await db.commit()
    seen = []

    async def provider(request):
        seen.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer sync-token":
            async with app.state.session_factory() as reconnect:
                await upsert_github_user(
                    reconnect,
                    app.state.cipher,
                    GitHubProfile(99, "sync-member", "Sync member", None, 0),
                    OAuthToken("reconnected-token", "read:user"),
                    sync_account.user_id,
                )
                assert await enqueue_initial_sync(reconnect, redis, sync_account.user_id) == job.id
            return httpx.Response(401)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await run_initial_sync(db, job.id, http, app.state.cipher)
    await db.refresh(job)
    await db.refresh(sync_account)
    assert job.status == "succeeded"
    assert sync_account.token_status == "valid"
    assert seen == ["Bearer sync-token", "Bearer reconnected-token"]
    assert len((await db.scalars(select(AnalysisJob))).all()) == 1


async def test_enqueue_failure_is_persisted_as_failed(db, sync_account):
    from app.core.errors import AppError
    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

    class UnavailableQueue:
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("Queue unavailable")

    with pytest.raises(AppError):
        await enqueue_initial_sync(db, UnavailableQueue(), sync_account.user_id)
    job = await db.scalar(select(AnalysisJob).where(AnalysisJob.user_id == sync_account.user_id))
    assert job.status == "failed"


async def test_worker_consumes_enqueued_job_and_relogin_can_retry_failure(
    db, app, redis, sync_account
):
    from arq.worker import Worker

    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync
    from app.workers.tasks.initial_sync import initial_sync

    first = await enqueue_initial_sync(db, redis, sync_account.user_id)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        worker = Worker(
            [initial_sync],
            redis_pool=redis,
            burst=True,
            handle_signals=False,
            poll_delay=0.01,
            ctx={
                "session_factory": app.state.session_factory,
                "http_client": http,
                "cipher": app.state.cipher,
            },
        )
        await worker.async_run()
        # The app fixture owns this Redis pool; burst mode has finished all jobs.
    failed = await db.get(AnalysisJob, first)
    assert failed.status == "failed"
    second = await enqueue_initial_sync(db, redis, sync_account.user_id)
    assert second != first
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    ) as http:
        worker = Worker(
            [initial_sync],
            redis_pool=redis,
            burst=True,
            handle_signals=False,
            poll_delay=0.01,
            ctx={
                "session_factory": app.state.session_factory,
                "http_client": http,
                "cipher": app.state.cipher,
            },
        )
        await worker.async_run()
    assert (await db.get(AnalysisJob, second)).status == "succeeded"


async def test_current_token_401_revokes_account_but_preserves_cached_repos(db, app, sync_account):
    from app.features.analysis.pipeline.initial_sync import run_initial_sync

    cached = Repository(
        user_id=sync_account.user_id, github_repo_id=5, name="old", full_name="u/old"
    )
    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add_all([cached, job])
    await db.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401))
    ) as http:
        await run_initial_sync(db, job.id, http, app.state.cipher)
    await db.refresh(sync_account)
    await db.refresh(cached)
    await db.refresh(job)
    assert sync_account.token_status == "revoked"
    assert cached.is_accessible is True
    assert job.status == "failed"
    assert job.error_code == "token_invalid"
