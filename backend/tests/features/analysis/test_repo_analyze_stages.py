"""L0-b의 commit과 L1 실행 경계를 실제 PostgreSQL에서 검증한다."""

import httpx
import pytest
from sqlalchemy import select, update

from app.db.models.knowledge import PromptVersion
from app.db.models.user import GithubAccount
from app.features.analysis.pipeline.steps import repo_analyze
from app.integrations.github.client import GithubClient
from app.llm_tasks.prompt_loader import PromptNotFoundError
from tests.features.analysis.test_repo_analyze import (
    SETTINGS,
    SHA,
    _github_reply,
    _model_reply,
    _read,
    _seed,
)


async def collect(sessions, run_id, *, batch_no=1, revoke=False):
    def handler(request):
        assert request.url.host == "api.github.com"
        return _github_reply(request, unauthorized=revoke and "author" in request.url.params)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await repo_analyze.collect_candidate_batch(
            sessions,
            run_id,
            batch_no,
            github_client=GithubClient("fixture-token", client=http),
            github_token_encrypted=b"fixture",
            login="owner",
        )


@pytest.mark.parametrize("revoke", [False, True])
async def test_collection_commits_without_a_prompt_and_later_failure_keeps_details(
    session_factory, revoke
):
    run_id, _ = await _seed(session_factory)
    async with session_factory.begin() as session:
        await session.execute(update(PromptVersion).values(is_active=False))

    collected = await collect(session_factory, run_id, revoke=revoke)
    candidates, analyses, repositories = await _read(session_factory, run_id)
    assert repositories[0].head_sha == SHA
    assert repositories[0].readme_text == "Python service README"
    assert "analysis" not in candidates[0].ranking_signals and analyses == []
    async with session_factory() as session:
        account = (await session.scalars(select(GithubAccount))).one()
        assert account.token_status == ("revoked" if revoke else "valid")

    def unexpected(request):
        raise AssertionError("프롬프트가 없으면 GitHub나 LLM을 호출하지 않는다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        with pytest.raises(PromptNotFoundError):
            await repo_analyze.analyze_collected_batch(
                session_factory, collected, settings=SETTINGS, http_client=http
            )
    _, analyses, repositories = await _read(session_factory, run_id)
    assert analyses == [] and repositories[0].head_sha == SHA
    async with session_factory() as session:
        account = (await session.scalars(select(GithubAccount))).one()
        assert account.token_status == ("revoked" if revoke else "valid")


async def test_analysis_uses_collected_details_and_then_reuses_exact_l1_cache(session_factory):
    run_id, repo_ids = await _seed(session_factory)
    collected = await collect(session_factory, run_id)

    def model_only(request):
        assert request.url.host != "api.github.com"
        return _model_reply(repo_ids)

    async with httpx.AsyncClient(transport=httpx.MockTransport(model_only)) as http:
        first = await repo_analyze.analyze_collected_batch(
            session_factory, collected, settings=SETTINGS, http_client=http
        )
    assert len(first) == 1 and first[0]["status"] == "succeeded"

    def unexpected(request):
        raise AssertionError("같은 수집 자료의 성공 캐시는 외부 I/O 없이 재사용한다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        repeated = await repo_analyze.analyze_collected_batch(
            session_factory, collected, settings=SETTINGS, http_client=http
        )
    candidates, analyses, _ = await _read(session_factory, run_id)
    assert repeated == first and len(analyses) == 1
    assert candidates[0].ranking_signals["existing"] == "kept"
    assert candidates[0].ranking_signals["analysis"]["analysis_id"] == str(analyses[0].id)


async def test_empty_batch_does_not_require_a_prompt_or_recommendations(session_factory):
    run_id, _ = await _seed(session_factory)
    async with session_factory.begin() as session:
        await session.execute(update(PromptVersion).values(is_active=False))
    collected = await collect(session_factory, run_id, batch_no=2)

    def unexpected(request):
        raise AssertionError("빈 batch는 외부 I/O를 수행하지 않는다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        assert (
            await repo_analyze.analyze_collected_batch(
                session_factory,
                collected,
                settings=SETTINGS,
                http_client=http,
                refresh_recommendations=True,
            )
            == []
        )
    _, analyses, _ = await _read(session_factory, run_id)
    assert analyses == []
