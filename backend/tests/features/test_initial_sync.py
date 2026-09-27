"""Public repository collection and its persisted background-job lifecycle."""

import asyncio
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
        # 선행 클라이언트에 순환 차단이 없어도 회귀 검증 자체는 유한 시간에 실패한다.
        assert len(destinations) <= 2, "GitHub pagination did not stop"
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


async def test_sync_persists_public_metadata_and_finishes_job(db, app, redis, sync_account):
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
        await run_initial_sync(db, job.id, http, app.state.cipher, redis=redis)
    await db.refresh(job)
    assert job.status == "succeeded"
    repos = (await db.scalars(select(Repository))).all()
    assert [repo.github_repo_id for repo in repos] == [11]
    assert repos[0].primary_language == "Python"
    await db.refresh(sync_account)
    assert sync_account.public_repo_count == 1


async def test_provider_401_revokes_only_the_token_used_by_that_request(
    db, app, redis, sync_account
):
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
        await run_initial_sync(db, job.id, http, app.state.cipher, redis=redis)
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
        await run_initial_sync(db, job.id, http, app.state.cipher, redis=redis)
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


async def test_current_token_401_revokes_account_but_preserves_cached_repos(
    db, app, redis, sync_account
):
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
        await run_initial_sync(db, job.id, http, app.state.cipher, redis=redis)
    await db.refresh(sync_account)
    await db.refresh(cached)
    await db.refresh(job)
    assert sync_account.token_status == "revoked"
    assert cached.is_accessible is True
    assert job.status == "failed"
    assert job.error_code == "token_invalid"


@pytest.mark.parametrize("failure", ["invalid_payload", "second_page"])
async def test_incomplete_listing_preserves_cached_repositories_and_count(
    db, app, redis, sync_account, failure
):
    from app.features.analysis.pipeline.initial_sync import run_initial_sync

    cached = Repository(
        user_id=sync_account.user_id,
        github_repo_id=5,
        name="old",
        full_name="user/old",
        readme_text="cached README",
        is_accessible=True,
    )
    sync_account.public_repo_count = 7
    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add_all([cached, job])
    await db.commit()

    def provider(request):
        if failure == "invalid_payload":
            return httpx.Response(200, json={"message": "not a repository list"})
        if request.url.params.get("page") == "2":
            return httpx.Response(500)
        return httpx.Response(
            200,
            json=[
                {
                    "id": 11,
                    "name": "visible",
                    "full_name": "user/visible",
                    "private": False,
                }
            ],
            headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await run_initial_sync(db, job.id, http, app.state.cipher, redis=redis)
    await db.refresh(job)
    await db.refresh(sync_account)
    await db.refresh(cached)
    assert job.status == "failed" and job.error_code == "repo_unreachable"
    assert cached.is_accessible is True and cached.readme_text == "cached README"
    assert sync_account.public_repo_count == 7
    # 완성되지 않은 목록으로 캐시를 제외하거나 일부 페이지를 새 목록으로 확정하지 않는다.
    assert (await db.scalars(select(Repository.github_repo_id))).all() == [5]


@pytest.mark.parametrize("reconnect_at", ["before_read", "after_read", "after_failure_commit"])
async def test_reconnect_keeps_a_runnable_sync_across_failure_boundary(
    db, app, redis, sync_account, reconnect_at
):
    from arq.jobs import Job
    from arq.worker import Worker

    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync
    from app.features.auth.oauth import GitHubProfile, OAuthToken
    from app.features.auth.service import upsert_github_user
    from app.workers.tasks.initial_sync import initial_sync

    job = AnalysisJob(user_id=sync_account.user_id, job_type="initial_sync", status="queued")
    db.add(job)
    await db.commit()
    job_id, user_id = job.id, sync_account.user_id
    reached = asyncio.Event()
    reconnected = asyncio.Event()

    async def pause_for_reconnect():
        reached.set()
        await asyncio.wait_for(reconnected.wait(), timeout=10)

    class BarrierSession:
        def __init__(self):
            self.db = app.state.session_factory()

        def __getattr__(self, name):
            return getattr(self.db, name)

        async def __aenter__(self):
            await self.db.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.db.__aexit__(*args)

        async def execute(self, statement, *args, **kwargs):
            result = await self.db.execute(statement, *args, **kwargs)
            columns = getattr(statement, "column_descriptions", [])
            if (
                reconnect_at == "after_read"
                and not reached.is_set()
                and [column["name"] for column in columns] == ["id", "access_token_encrypted"]
            ):
                # SELECT가 옛 토큰을 반환한 직후 재연동을 완료해 실제 경합 순서를 고정한다.
                await pause_for_reconnect()
            return result

        async def commit(self):
            await self.db.commit()
            if reconnect_at == "after_failure_commit" and not reached.is_set():
                async with app.state.session_factory() as verify:
                    status = await verify.scalar(
                        select(AnalysisJob.status).where(AnalysisJob.id == job_id)
                    )
                if status == "failed":
                    await pause_for_reconnect()

    async def reconnect():
        await asyncio.wait_for(reached.wait(), timeout=10)
        async with app.state.session_factory() as session:
            await upsert_github_user(
                session,
                app.state.cipher,
                GitHubProfile(99, "sync-member", "Sync member", None, 0),
                OAuthToken("new-sync-token", "read:user"),
                user_id,
            )
            await enqueue_initial_sync(session, redis, user_id)
        reconnected.set()

    async def provider(request):
        if request.headers["authorization"] == "Bearer sync-token":
            if reconnect_at == "before_read":
                await pause_for_reconnect()
            return httpx.Response(401)
        assert request.headers["authorization"] == "Bearer new-sync-token"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 11,
                    "name": "visible",
                    "full_name": "user/visible",
                    "private": False,
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        context = {
            "session_factory": BarrierSession,
            "http_client": http,
            "cipher": app.state.cipher,
            "redis": redis,
        }
        await asyncio.wait_for(
            asyncio.gather(initial_sync(context, str(job_id)), reconnect()), timeout=20
        )
        async with app.state.session_factory() as verify:
            jobs = (
                await verify.scalars(select(AnalysisJob).where(AnalysisJob.user_id == user_id))
            ).all()
        assert len(jobs) == (1 if reconnect_at == "before_read" else 2)
        for queued in (item for item in jobs if item.status == "queued"):
            info = await Job(f"initial_sync:{queued.id}", redis).info()
            assert info is not None and info.args == (str(queued.id),)
        # 후속 예약이 존재하는 것에 그치지 않고 실제 ARQ가 새 토큰으로 수집을 끝내야 한다.
        worker = Worker(
            [initial_sync],
            redis_pool=redis,
            burst=True,
            handle_signals=False,
            poll_delay=0.01,
            ctx={**context, "session_factory": app.state.session_factory},
        )
        await worker.async_run()
    async with app.state.session_factory() as verify:
        statuses = (
            await verify.scalars(select(AnalysisJob.status).where(AnalysisJob.user_id == user_id))
        ).all()
        assert statuses.count("succeeded") == 1
        assert all(status in {"succeeded", "failed"} for status in statuses)
        account = await verify.scalar(select(GithubAccount).where(GithubAccount.user_id == user_id))
        assert account.token_status == "valid"
        assert app.state.cipher.decrypt(account.access_token_encrypted) == "new-sync-token"
        repo = await verify.scalar(select(Repository).where(Repository.user_id == user_id))
        assert repo.github_repo_id == 11
