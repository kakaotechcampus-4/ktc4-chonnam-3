"""L1은 동일 SHA의 실제 구조·설정 원문을 제한된 범위에서 수집한다."""

import base64
import hashlib

import httpx

from app.integrations.github.base import RepoSummary
from app.integrations.github.client import GithubClient
from app.integrations.github.snapshot import collect_snapshot_context


async def test_tree_size_skips_unreadable_file_without_spending_contents_request():
    sha, tree = "a" * 40, "b" * 40
    small = b"service=true\n"
    large = b"x" * 65536
    blobs = {
        path: hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        for path, data in (("a.config", large), ("b.config", small))
    }
    calls = []

    def handler(request):
        path = request.url.path.removeprefix("/repos/o/r")
        calls.append(path)
        if path == f"/git/commits/{sha}":
            return httpx.Response(200, json={"sha": sha, "tree": {"sha": tree}})
        if path == f"/git/trees/{tree}":
            return httpx.Response(
                200,
                json={
                    "sha": tree,
                    "truncated": False,
                    "tree": [
                        {
                            "path": path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": blobs[path],
                            "size": len(data),
                        }
                        for path, data in (("a.config", large), ("b.config", small))
                    ],
                },
            )
        path = path.removeprefix("/contents/")
        raw = large if path == "a.config" else small
        return httpx.Response(
            200,
            json={
                "type": "file",
                "path": path,
                "sha": blobs[path],
                "encoding": "base64",
                "size": len(raw),
                "content": base64.b64encode(raw).decode(),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = GithubClient("fixture", client=http)
        structure, files, limitations = await collect_snapshot_context(
            "o/r", sha, client._snapshot_json, max_requests=3, max_files=1
        )
    assert structure == ("a.config", "b.config")
    assert [item.path for item in files] == ["b.config"]
    assert "/contents/a.config" not in calls
    assert calls == [f"/git/commits/{sha}", f"/git/trees/{tree}", "/contents/b.config"]
    assert limitations


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
