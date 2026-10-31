"""준비 원문 수집은 공개 앱 인증을 사용하고 private 전환·설정 오류를 고정 사유로 거절한다."""

import base64
import hashlib
from uuid import UUID

import httpx
import pytest
from devon_ai import contracts as c

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.features.interview.repository_sources import (
    SourcePreparationError,
    collect_repository_sources,
)
from app.integrations.llm.client import CallBudget

SHA, TREE = "a" * 40, "b" * 40
TEXT = b"print('fixture')\n"
BLOB = hashlib.sha1(f"blob {len(TEXT)}\0".encode() + TEXT).hexdigest()
REPOSITORY_ID = str(UUID(int=1))
APP_AUTH = "Basic " + base64.b64encode(b"fixture-app-id:fixture-app-secret").decode()


class Provider:
    def __init__(self, auth, outcome=None):
        self.auth, self.outcome = auth, outcome
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        assert request.url.host == "api.github.com" and request.method == "GET"
        assert request.headers.get("Authorization") == self.auth
        assert "cookie" not in request.headers
        assert "fixture-app-secret" not in str(request.url)
        suffix = request.url.path.removeprefix("/repos/owner/sample")
        if not suffix:
            if self.outcome in {"metadata403", "metadata404"}:
                return httpx.Response(int(self.outcome[-3:]), text="fixture-app-secret")
            return httpx.Response(
                200,
                json={"id": 123, "private": self.outcome == "private"},
                headers={"Set-Cookie": "source=private-cookie"},
            )
        if suffix == f"/git/commits/{SHA}":
            return httpx.Response(200, json={"sha": SHA, "tree": {"sha": TREE}})
        if suffix == f"/git/trees/{TREE}":
            return httpx.Response(
                200,
                json={
                    "sha": TREE,
                    "truncated": False,
                    "tree": [{"path": "src.py", "mode": "100644", "type": "blob", "sha": BLOB}],
                },
            )
        assert suffix == "/contents/src.py" and request.url.params["ref"] == SHA
        if self.outcome in {"content403", "content404"}:
            return httpx.Response(int(self.outcome[-3:]), text="fixture-app-secret")
        return httpx.Response(
            200,
            json={
                "type": "file",
                "path": "src.py",
                "sha": BLOB,
                "size": len(TEXT),
                "encoding": "base64",
                "content": base64.b64encode(TEXT).decode(),
            },
        )


async def collect(provider, *, client_id="fixture-app-id", client_secret="fixture-app-secret"):
    config = Settings(
        _env_file=None, github_client_id=client_id, github_client_secret=client_secret
    )
    shallow = c.ShallowRepoAnalysis(
        REPOSITORY_ID,
        SHA,
        "fixture",
        ("출력",),
        ("backend",),
        ("Python",),
        "출력 예제",
        (c.ShallowBasis("readme", "출력 예제"),),
        (),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider),
        auth=("inherited-user", "private-user-token"),
        cookies={"inherited": "private-cookie"},
        follow_redirects=True,
    ) as http:
        return await collect_repository_sources(
            scope=EvidenceScope(REPOSITORY_ID, 123, "owner/sample", SHA, frozenset()),
            shallow=shallow,
            prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
            settings=config,
            http_client=http,
            budget=CallBudget(),
            paths=("src.py",),
        )


async def test_collection_authenticates_metadata_commit_tree_and_source_with_public_app():
    provider = Provider(APP_AUTH)
    result = await collect(provider)
    assert result.item.sources == (
        c.SourceDocument("src.py", "file", TEXT.decode(), "entire file"),
    )
    assert len(provider.requests) == 4


async def test_unconfigured_app_preserves_anonymous_collection_without_inherited_credentials():
    provider = Provider(None)
    result = await collect(provider, client_id="", client_secret="")
    assert len(result.item.sources) == 1 and len(provider.requests) == 4


@pytest.mark.parametrize("missing", ["client_id", "client_secret"])
async def test_partial_app_settings_fail_before_http_instead_of_falling_back_to_anonymous(missing):
    provider = Provider(None)
    credentials = {"client_id": "fixture-app-id", "client_secret": "fixture-app-secret"}
    credentials[missing] = ""
    with pytest.raises(SourcePreparationError) as caught:
        await collect(provider, **credentials)
    assert caught.value.code == "github_credentials_invalid"
    assert str(caught.value) == "github_credentials_invalid"
    assert provider.requests == []


@pytest.mark.parametrize(
    ("outcome", "code", "requests"),
    [
        ("private", "repository_unavailable", 1),
        ("metadata403", "github_http_403", 1),
        ("metadata404", "repository_unavailable", 1),
        ("content403", "repository_sources_unavailable", 4),
        ("content404", "repository_sources_unavailable", 4),
    ],
)
async def test_private_or_inaccessible_sources_never_echo_app_credentials(outcome, code, requests):
    provider = Provider(APP_AUTH, outcome)
    with pytest.raises(SourcePreparationError) as caught:
        await collect(provider)
    assert caught.value.code == code and len(provider.requests) == requests
    assert "fixture-app-secret" not in str(caught.value) + repr(caught.value.limitations)
