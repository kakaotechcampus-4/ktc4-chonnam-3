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


async def test_fixed_commit_regular_file_and_original_text_have_verified_provenance():
    scope = tools.EvidenceScope(
        "repository-1", 42, "owner/project", COMMIT, frozenset({"README.md", "src/app.py"})
    )
    limits = tools.EvidenceLimits(12, 2, 8192, 32768, 1.0)
    result, seen = await run(scope, limits, paths=("README.md", "src/app.py"))
    assert result.status == "found"
    assert [(item.path, item.content) for item in result.items] == [
        ("README.md", "hello\n"),
        ("src/app.py", "hello\n"),
    ]
    assert all(item.git_ref == COMMIT and item.evidence_id is None for item in result.items)
    assert all(item.start_line == item.end_line == 1 for item in result.items)
    assert all(item.tool_name == "read_file" for item in result.items)
    assert seen[0].headers["Authorization"] == "Bearer explicit-token"
    assert all(
        "authorization" not in req.headers and "cookie" not in req.headers for req in seen[1:]
    )
    assert all(req.url.host == "api.github.com" and req.url.scheme == "https" for req in seen)
    assert [req.url.params["ref"] for req in seen if "/contents/" in req.url.path] == [
        COMMIT,
        COMMIT,
    ]
    assert sum(req.url.path.endswith(ROOT_TREE) for req in seen) == 1
    assert all("recursive" not in req.url.params for req in seen)


@pytest.mark.parametrize(
    "change",
    [
        {"repository_id": "another"},
        {"git_ref": "d" * 40},
        {"allowed_paths": ("README.md", "outside.py")},
    ],
)
async def test_model_cannot_expand_service_scope(scope, limits, change):
    with pytest.raises(ContractError):
        await run(scope, limits, request=replace(verification(scope), **change), responses={})


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        "a/../b",
        "a\\b",
        "a//b",
        "https://evil.test/a",
        "a%2fb",
        "a\x00b",
        "a\ud800b",
        "src/",
    ],
)
async def test_noncanonical_paths_are_rejected_before_http(scope, limits, path):
    with pytest.raises(ContractError):
        unsafe = replace(scope, allowed_paths=frozenset({path}))
        await run(unsafe, limits, paths=(path,), responses={})


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_requests", True),
        ("max_files", 0),
        ("max_response_bytes", -1),
        ("max_total_bytes", 1.5),
        ("timeout_seconds", True),
        ("timeout_seconds", float("inf")),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", 10**500),
    ],
)
def test_unbounded_or_mistyped_limits_are_rejected(limits, field, value):
    with pytest.raises(ContractError):
        replace(limits, **{field: value})


@pytest.mark.parametrize("change", [{"private": True}, {"id": 43}, {"visibility": "internal"}])
async def test_repository_identity_and_public_status_precede_content_access(scope, limits, change):
    responses = replies()
    responses[REPO].update(change)
    result, seen = await run(scope, limits, responses=responses)
    assert result.status == "tool_error" and not result.items
    assert len(seen) == 1


@pytest.mark.parametrize(
    "mode,kind", [("120000", "blob"), ("160000", "commit"), ("040000", "tree")]
)
async def test_symlink_submodule_and_directory_are_never_read_as_files(scope, limits, mode, kind):
    responses = replies()
    responses[f"{REPO}/git/trees/{ROOT_TREE}"]["tree"][0].update(mode=mode, type=kind)
    result, seen = await run(scope, limits, responses=responses)
    assert result.status == "tool_error" and not result.items
    assert not any("/contents/" in req.url.path for req in seen)


@pytest.mark.parametrize(
    "change",
    [
        {"sha": "d" * 40},
        {"path": "outside.py"},
        {"type": "dir"},
        {"encoding": "none"},
        {"content": "aW52YWxpZA=="},
        {"content": "!bad!"},
        {"size": 7},
    ],
)
async def test_invalid_content_is_not_valid_evidence(scope, limits, change):
    responses = replies()
    responses[f"{REPO}/contents/README.md"].update(change)
    result, _ = await run(scope, limits, responses=responses)
    assert result.status == "tool_error" and not result.items


async def test_source_line_numbers_only_count_lf_boundaries(scope, limits):
    responses = replies()
    blob = "d842e9f512737cee113acd286f06c708d1f9328e"
    responses[f"{REPO}/git/trees/{ROOT_TREE}"]["tree"][0]["sha"] = blob
    responses[f"{REPO}/contents/README.md"].update(sha=blob, content="YeKAqGIK")
    result, _ = await run(scope, limits, responses=responses)
    assert result.items[0].content == "a\u2028b\n"
    assert result.items[0].start_line == result.items[0].end_line == 1


async def test_missing_file_is_not_found_but_missing_snapshot_is_insufficient(scope, limits):
    responses = replies()
    responses[f"{REPO}/git/trees/{ROOT_TREE}"]["tree"] = []
    result, _ = await run(scope, limits, responses=responses)
    assert result.status == "not_found" and result.searched_scope and not result.items
    responses[f"{REPO}/git/commits/{COMMIT}"] = httpx.Response(404)
    result, _ = await run(scope, limits, responses=responses)
    assert result.status == "insufficient_analysis" and result.limitations and not result.items


@pytest.mark.parametrize("status", [302, 403, 404, 429, 500])
async def test_error_after_first_file_keeps_valid_items_and_never_retries(scope, limits, status):
    responses = replies()
    responses[f"{REPO}/contents/src/app.py"] = httpx.Response(
        status, headers={"Location": "https://evil.test/private", "Retry-After": "600"}
    )
    result, seen = await run(scope, limits, paths=("README.md", "src/app.py"), responses=responses)
    assert result.status == "tool_error" and result.error_code and result.limitations
    assert [item.path for item in result.items] == ["README.md"]
    assert sum(req.url.path.endswith("contents/src/app.py") for req in seen) == 1
    assert all(req.url.host == "api.github.com" for req in seen)


@pytest.mark.parametrize("field,value", [("max_requests", 4), ("max_files", 1)])
async def test_limits_stop_remaining_paths_and_preserve_previous_evidence(
    scope, limits, field, value
):
    result, seen = await run(
        scope, replace(limits, **{field: value}), paths=("README.md", "src/app.py")
    )
    assert result.status == "tool_error" and result.limitations
    assert [item.path for item in result.items] == ["README.md"]
    assert "src/app.py" not in result.searched_scope
    if field == "max_requests":
        assert len(seen) == 4


async def test_private_transition_cannot_use_the_users_credentials(scope, limits):
    responses = replies()

    async def handler(req):
        if "/contents/" in req.url.path:
            assert "authorization" not in req.headers and "cookie" not in req.headers
            return httpx.Response(404)
        return httpx.Response(200, json=responses[req.url.path])

    result, _ = await run(scope, limits, handler=handler)
    assert result.status == "tool_error" and result.error_code == "github_file_unavailable"
    assert not result.items


async def test_timeout_and_cancellation_are_distinct_and_do_not_leak_secrets(scope, limits, caplog):
    async def timeout(req):
        raise httpx.ReadTimeout("explicit-token private-body", request=req)

    result, _ = await run(scope, limits, handler=timeout)
    assert result.status == "tool_error" and result.error_code == "github_timeout"
    assert "explicit-token" not in repr(result) + caplog.text

    async def cancel(req):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run(scope, limits, handler=cancel)


@pytest.mark.parametrize(
    "entries",
    [
        [None],
        [{"path": 123}],
        [{"path": "README.md"}],
        [{"path": "README.md", "mode": [], "type": "blob", "sha": BLOB}],
        [{"path": "README.md", "mode": {}, "type": "blob", "sha": BLOB}],
    ],
)
async def test_malformed_tree_is_not_reported_as_absent_file(scope, limits, entries):
    responses = replies()
    responses[f"{REPO}/git/trees/{ROOT_TREE}"]["tree"] = entries
    result, _ = await run(scope, limits, responses=responses)
    assert result.status == "tool_error" and not result.items


class Chunks(httpx.AsyncByteStream):
    def __init__(self):
        self.read = 0

    async def __aiter__(self):
        for _ in range(10):
            self.read += 1
            yield b"x" * 128


async def test_response_byte_limit_stops_stream_consumption(scope, limits):
    chunks = Chunks()
    result, _ = await run(
        scope,
        replace(limits, max_response_bytes=200),
        responses={REPO: httpx.Response(200, stream=chunks)},
    )
    assert result.status == "tool_error" and result.error_code == "evidence_byte_limit"
    assert chunks.read == 2


async def test_total_byte_budget_includes_metadata_and_tree_responses(scope, limits):
    responses = replies()
    used = sum(
        len(httpx.Response(200, json=responses[path]).content)
        for path in (
            REPO,
            f"{REPO}/git/commits/{COMMIT}",
            f"{REPO}/git/trees/{ROOT_TREE}",
            f"{REPO}/contents/README.md",
        )
    )
    result, seen = await run(
        scope, replace(limits, max_total_bytes=used), paths=("README.md", "src/app.py")
    )
    assert result.status == "tool_error" and result.error_code == "evidence_budget_exhausted"
    assert [item.path for item in result.items] == ["README.md"]
    assert len(seen) == 4


async def test_overall_deadline_preserves_first_file_and_stops_slow_next_file(scope, limits):
    responses = replies()

    async def slow(req):
        if req.url.path.endswith("contents/src/app.py"):
            await asyncio.Event().wait()
        return httpx.Response(200, json=responses[req.url.path])

    result, _ = await run(
        scope,
        replace(limits, timeout_seconds=0.02),
        paths=("README.md", "src/app.py"),
        handler=slow,
    )
    assert result.status == "tool_error" and result.error_code == "github_timeout"
    assert [item.path for item in result.items] == ["README.md"]


async def test_duplicate_repository_fields_do_not_hide_private_status(scope, limits):
    body = json.dumps(replies()[REPO]).replace(
        '"private": false', '"private": true, "private": false'
    )
    result, seen = await run(scope, limits, responses={REPO: httpx.Response(200, content=body)})
    assert result.status == "tool_error" and not result.items and len(seen) == 1
