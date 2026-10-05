"""고정 SHA의 허용 파일만 읽는 실제 HTTP 경계. DB와 외부 네트워크는 사용하지 않는다."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from devon_ai.contracts import ContractError, VerificationRequest
from pydantic import SecretStr

from app.agents.director import tools

COMMIT = "a" * 40
ROOT_TREE = "b" * 40
SRC_TREE = "c" * 40
BLOB = "ce013625030ba8dba906f756967f9e9ca394464a"
REPO = "/repos/owner/project"


@pytest.fixture
def scope():
    return tools.EvidenceScope(
        "repository-1", 42, "owner/project", COMMIT, frozenset({"README.md", "src/app.py"})
    )


@pytest.fixture
def limits():
    return tools.EvidenceLimits(12, 2, 8192, 32768, 1.0)


def verification(scope):
    return VerificationRequest(
        "코드를 확인합니다",
        "구현 확인",
        scope.repository_id,
        COMMIT,
        tuple(sorted(scope.allowed_paths)),
    )


def replies():
    return {
        REPO: {"id": 42, "full_name": "owner/project", "private": False, "visibility": "public"},
        f"{REPO}/git/commits/{COMMIT}": {"sha": COMMIT, "tree": {"sha": ROOT_TREE}},
        f"{REPO}/git/trees/{ROOT_TREE}": {
            "sha": ROOT_TREE,
            "truncated": False,
            "tree": [
                {"path": "README.md", "mode": "100644", "type": "blob", "sha": BLOB},
                {"path": "src", "mode": "040000", "type": "tree", "sha": SRC_TREE},
            ],
        },
        f"{REPO}/git/trees/{SRC_TREE}": {
            "sha": SRC_TREE,
            "truncated": False,
            "tree": [{"path": "app.py", "mode": "100755", "type": "blob", "sha": BLOB}],
        },
        **{
            f"{REPO}/contents/{path}": {
                "type": "file",
                "encoding": "base64",
                "size": 6,
                "path": path,
                "sha": BLOB,
                "content": "aGVsbG8K\n",
            }
            for path in ("README.md", "src/app.py")
        },
    }


async def run(scope, limits, *, paths=("README.md",), responses=None, request=None, handler=None):
    responses = replies() if responses is None else responses
    seen = []

    async def respond(req):
        seen.append(req)
        if handler is not None:
            return await handler(req)
        value = responses[req.url.path]
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        auth=("client-user", "client-password"),
        headers={"Authorization": "Bearer client-default", "Cookie": "session=private"},
        follow_redirects=True,
    ) as http:
        result = await tools.read_files(
            verification(scope) if request is None else request,
            scope=scope,
            paths=paths,
            limits=limits,
            http_client=http,
            access_token=SecretStr("explicit-token"),
        )
    return result, seen
