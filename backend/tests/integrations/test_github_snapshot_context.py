"""L1은 동일 SHA의 실제 구조·설정 원문을 제한된 범위에서 수집한다."""

import base64
import hashlib

import httpx

from app.integrations.github.base import RepoSummary
from app.integrations.github.client import GithubClient


async def test_l1_snapshot_pins_readme_and_nested_supporting_text_to_one_sha():
    sha, tree, subtree = "a" * 40, "b" * 40, "c" * 40
    content = '{"service": "orders", "dependencies": ["sql"]}\n'
    raw = content.encode()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path.removeprefix("/repos/o/r")
        if path == "/commits/main":
            return httpx.Response(200, json={"sha": sha})
        if path == "/languages":
            return httpx.Response(200, json={"Python": 10})
        if path == "/readme":
            assert request.url.params["ref"] == sha
            return httpx.Response(200, json={"encoding": "utf-8", "content": "Order service"})
        if path == "/commits":
            return httpx.Response(200, json=[])
        if path == f"/git/commits/{sha}":
            return httpx.Response(200, json={"sha": sha, "tree": {"sha": tree}})
        if path == f"/git/trees/{tree}":
            return httpx.Response(
                200,
                json={
                    "sha": tree,
                    "truncated": False,
                    "tree": [{"path": "units", "mode": "040000", "type": "tree", "sha": subtree}],
                },
            )
        if path == f"/git/trees/{subtree}":
            return httpx.Response(
                200,
                json={
                    "sha": subtree,
                    "truncated": False,
                    "tree": [
                        {
                            "path": "custom.manifest",
                            "mode": "100644",
                            "type": "blob",
                            "sha": blob,
                            "size": len(raw),
                        }
                    ],
                },
            )
        if path == "/contents/units/custom.manifest":
            assert request.url.params["ref"] == sha
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "units/custom.manifest",
                    "sha": blob,
                    "encoding": "base64",
                    "size": len(raw),
                    "content": base64.b64encode(raw).decode(),
                },
            )
        raise AssertionError(path)

    repo = RepoSummary(1, "r", "o/r", default_branch="main")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GithubClient("fixture", client=client).fetch_repo_detail(
            repo, include_context=True
        )
    assert result.head_sha == sha
    assert result.structure == ("units/", "units/custom.manifest")
    assert result.supporting_files[0].path == "units/custom.manifest"
    assert result.supporting_files[0].content == content
    assert [r.url.path for r in calls].index("/repos/o/r/commits/main") < [
        r.url.path for r in calls
    ].index("/repos/o/r/readme")
    assert not result.source_limitations
