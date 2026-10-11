"""수집 재시도의 실패와 새 자료 확인을 실제 PostgreSQL에서 구분한다."""

import httpx
import pytest
from sqlalchemy import select

from app.db.models.analysis import RepoMatchScore
from app.db.models.user import GithubAccount
from app.features.analysis.cards import get_repository_cards
from app.features.analysis.pipeline.steps import repo_analyze
from app.integrations.github.client import GithubClient
from tests.features.analysis.test_repo_analyze import (
    SETTINGS,
    SHA,
    _another_run,
    _github_reply,
    _read,
)
from tests.features.analysis.test_repo_analyze_atomic import analyze, seed_pages
from tests.features.analysis.test_repo_analyze_stages import collect


async def _success(sessions):
    run_id, repo_ids = await seed_pages(sessions)
    await analyze(sessions, await collect(sessions, run_id), repo_ids[:1])
    return run_id, repo_ids


async def _collect(sessions, run_id, handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await repo_analyze.collect_candidate_batch(
            sessions,
            run_id,
            1,
            github_client=GithubClient("fixture-token", client=http),
            github_token_encrypted=b"fixture",
            login="owner",
        )


async def _bind_without_llm(sessions, collected, *, refresh=False):
    def unexpected(request):
        raise AssertionError("SHA를 확인하지 못한 재시도에서 LLM을 호출하면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        return await repo_analyze.analyze_collected_batch(
            sessions,
            collected,
            settings=SETTINGS,
            http_client=http,
            refresh_recommendations=refresh,
        )


def _details(repo):
    return (
        repo.languages,
        repo.readme_text,
        repo.readme_truncated,
        repo.head_sha,
        repo.commit_count,
        repo.user_commit_count,
    )


@pytest.mark.parametrize("status", [429, 401])
@pytest.mark.parametrize("refresh", [False, True])
async def test_unverified_retry_preserves_success_details_and_recommendations(
    session_factory, status, refresh
):
    run_id, _ = await _success(session_factory)
    candidates, analyses, repositories = await _read(session_factory, run_id)
    original_snapshot = candidates[0].ranking_signals["analysis"].copy()
    original_details = _details(repositories[0])
    original_analysis_id = analyses[0].id
    async with session_factory.begin() as session:
        original_card = (await get_repository_cards(session, run_id))[0]
        original_matches = {
            row.repository_id: row.id for row in await session.scalars(select(RepoMatchScore))
        }

    def blocked(request):
        assert request.url.host == "api.github.com"
        return httpx.Response(
            status,
            headers={"retry-after": "60"} if status == 429 else {},
            json={"message": "retry rejected"},
        )

    collected = await _collect(session_factory, run_id, blocked)
    assert collected.inputs == []
    bound = await _bind_without_llm(session_factory, collected, refresh=refresh)
    candidates, analyses, repositories = await _read(session_factory, run_id)
    assert bound == [original_snapshot]
    assert candidates[0].ranking_signals["analysis"] == original_snapshot
    assert [row.id for row in analyses] == [original_analysis_id]
    assert _details(repositories[0]) == original_details
    async with session_factory.begin() as session:
        assert (await get_repository_cards(session, run_id))[0] == original_card
        assert {
            row.repository_id: row.id for row in await session.scalars(select(RepoMatchScore))
        } == original_matches
        account = (await session.scalars(select(GithubAccount))).one()
        assert account.token_status == ("revoked" if status == 401 else "valid")


@pytest.mark.parametrize("status", [503, 404])
async def test_readme_failure_is_distinguished_from_confirmed_absence(session_factory, status):
    run_id, _ = await _success(session_factory)

    def readme_failure(request):
        if request.url.path.endswith("/readme"):
            return httpx.Response(status, json={"message": "unavailable"})
        return _github_reply(request)

    collected = await _collect(session_factory, run_id, readme_failure)
    _, _, repositories = await _read(session_factory, run_id)
    # 일시 오류는 이전 내용을 살리고, 실제 README 부재가 확인되면 비운다.
    assert repositories[0].readme_text == ("Python service README" if status == 503 else None)
    assert repositories[0].readme_truncated is False
    assert len(collected.inputs) == 1
    assert collected.inputs[0].readme_text is None
    assert collected.inputs[0].collection_errors


async def test_new_sha_does_not_retain_counts_from_the_previous_sha(session_factory):
    run_id, _ = await _success(session_factory)
    new_sha = "b" * 40

    def changed_without_counts(request):
        if request.url.path.endswith("/commits"):
            return httpx.Response(503, json={"message": "unavailable"})
        return _github_reply(request, sha=new_sha)

    collected = await _collect(session_factory, run_id, changed_without_counts)
    _, _, repositories = await _read(session_factory, run_id)
    assert repositories[0].head_sha == new_sha
    assert repositories[0].commit_count is None
    assert repositories[0].user_commit_count is None
    assert len(collected.inputs) == 1 and collected.inputs[0].head_sha == new_sha


async def test_unconfirmed_sha_does_not_pair_new_counts_with_saved_sha(session_factory):
    run_id, _ = await _success(session_factory)

    def missing_sha(request):
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(503, json={"message": "unavailable"})
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[{"sha": "b" * 40}, {"sha": SHA}])
        return _github_reply(request)

    collected = await _collect(session_factory, run_id, missing_sha)
    _, _, repositories = await _read(session_factory, run_id)
    assert collected.inputs == []
    # 새 커밋 수를 읽었더라도 어느 SHA의 값인지 확인되지 않으면 이전 짝을 유지한다.
    assert (repositories[0].head_sha, repositories[0].commit_count) == (SHA, 1)
    assert repositories[0].user_commit_count == 1


@pytest.mark.parametrize("status", [429, 503])
async def test_earlier_readme_absence_does_not_hide_unverified_sha_failure(session_factory, status):
    run_id, _ = await _success(session_factory)
    candidates, _, _ = await _read(session_factory, run_id)
    original_snapshot = candidates[0].ranking_signals["analysis"].copy()

    def blocked_after_readme(request):
        if request.url.path.endswith("/readme"):
            return _github_reply(request, missing_readme=True)
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(status, headers={"retry-after": "60"}, json={})
        return _github_reply(request)

    collected = await _collect(session_factory, run_id, blocked_after_readme)
    assert collected.inputs == []
    assert collected.details["owner/repo0"].errors == [
        "no_readme",
        "rate_limited" if status == 429 else "repo_unreachable",
    ]
    assert await _bind_without_llm(session_factory, collected) == [original_snapshot]
    _, _, repositories = await _read(session_factory, run_id)
    # README 부재는 반영하되 확인하지 못한 SHA로 기존 분석·추천까지 실패 처리하지 않는다.
    assert repositories[0].readme_text is None
    async with session_factory.begin() as session:
        assert (await get_repository_cards(session, run_id))[0].recommended


async def test_new_run_cannot_inherit_success_when_collection_fails(session_factory):
    old_run, repo_ids = await _success(session_factory)
    new_run = await _another_run(session_factory, old_run, repo_ids[0])
    collected = await _collect(
        session_factory,
        new_run,
        lambda request: httpx.Response(
            429, headers={"retry-after": "60"}, json={"message": "rate limited"}
        ),
    )
    bound = await _bind_without_llm(session_factory, collected)
    candidates, analyses, _ = await _read(session_factory, new_run)
    assert bound[0]["status"] == "failed" and bound[0]["analysis_id"] is None
    assert candidates[0].ranking_signals["analysis"]["error_code"] == "rate_limited"
    assert len(analyses) == 1 and analyses[0].status == "succeeded"


async def test_verified_new_sha_failure_replaces_the_old_success_binding(session_factory):
    run_id, _ = await _success(session_factory)
    new_sha = "b" * 40
    collected = await _collect(
        session_factory, run_id, lambda request: _github_reply(request, sha=new_sha)
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"error": {"message": "fixture rejection"}})
        )
    ) as http:
        bound = await repo_analyze.analyze_collected_batch(
            session_factory,
            collected,
            settings=SETTINGS,
            http_client=http,
            refresh_recommendations=True,
        )
    assert bound[0]["status"] == "failed" and bound[0]["head_sha"] == new_sha
    async with session_factory.begin() as session:
        card = (await get_repository_cards(session, run_id))[0]
        assert card.status == "failed" and not card.recommended


async def test_confirmed_inaccessible_repository_is_not_kept_as_success(session_factory):
    run_id, _ = await _success(session_factory)
    collected = await _collect(
        session_factory,
        run_id,
        lambda request: _github_reply(request, inaccessible=True),
    )
    bound = await _bind_without_llm(session_factory, collected, refresh=True)
    candidates, analyses, repositories = await _read(session_factory, run_id)
    assert bound[0]["status"] == "failed"
    assert candidates[0].filter_status == "excluded"
    assert candidates[0].filter_reason == "inaccessible"
    assert repositories[0].is_accessible is False
    assert analyses[0].status == "succeeded"
    async with session_factory.begin() as session:
        assert await get_repository_cards(session, run_id) == []
        assert not any(row.is_recommended for row in await session.scalars(select(RepoMatchScore)))
