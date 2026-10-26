"""정상 빈 값은 저장하고, 저장할 수 없는 재수집 값은 기존 자료를 지우지 않는다."""

import base64

import httpx
import pytest

from app.features.analysis.pipeline.steps.repo_analyze import collect_candidate_batch
from app.integrations.github.client import GithubClient
from tests.features.analysis.test_repo_analyze import (
    SHA,
    _github_reply,
    _model_reply,
    _read,
    _run,
    _seed,
)


async def seeded_collection(sessions):
    run_id, repo_ids = await _seed(sessions)
    await _run(
        sessions,
        run_id,
        lambda request: (
            _github_reply(request)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        ),
    )
    return run_id


async def collect(sessions, run_id, handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await collect_candidate_batch(
            sessions,
            run_id,
            1,
            github_client=GithubClient("fixture", client=client),
            github_token_encrypted=b"fixture",
            login="owner",
        )


async def test_confirmed_empty_values_replace_previous_values(session_factory):
    run_id = await seeded_collection(session_factory)

    def handler(request):
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/readme"):
            return httpx.Response(200, json={"encoding": "base64", "content": ""})
        if request.url.path.endswith("/commits"):
            return httpx.Response(409, json={"message": "Git Repository is empty."})
        return _github_reply(request)

    await collect(session_factory, run_id, handler)
    _, _, repos = await _read(session_factory, run_id)
    assert repos[0].languages == {}
    assert repos[0].readme_text == "" and not repos[0].readme_truncated
    assert repos[0].head_sha == SHA
    assert repos[0].commit_count == repos[0].user_commit_count == 0


@pytest.mark.parametrize("invalid", ["readme", "sha", "languages"])
async def test_unstorable_collection_preserves_previous_field(session_factory, invalid):
    run_id = await seeded_collection(session_factory)

    def handler(request):
        if invalid == "readme" and request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json={"encoding": "base64", "content": base64.b64encode(b"bad\x00text").decode()},
            )
        if invalid == "sha" and "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "not-a-valid-sha"})
        if invalid == "languages" and request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"bad\x00language": 10})
        return _github_reply(request)

    collected = await collect(session_factory, run_id, handler)
    _, _, repos = await _read(session_factory, run_id)
    assert repos[0].readme_text == "Python service README"
    assert repos[0].head_sha == SHA and repos[0].commit_count == 1
    assert repos[0].languages == {"Python": 100}
    if invalid == "readme":
        assert collected.inputs[0].readme_text is None
        assert "no_readme" in collected.inputs[0].collection_errors
    elif invalid == "sha":
        assert collected.inputs == []
    else:
        assert collected.inputs[0].languages == ()
        assert "repo_unreachable" in collected.inputs[0].collection_errors
