"""구조 열거는 항목·깊이·요청 상한에서 멈추고 미방문 범위와 읽지 않은 항목을 한계로 전달한다."""

from uuid import UUID

import httpx
import pytest

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.features.interview.repository_sources import _structure
from app.integrations.github.evidence import EvidenceReader, EvidenceReadError


@pytest.mark.parametrize("cap", [2, 512])
@pytest.mark.parametrize("layout", ["flat", "queued", "overflow"])
async def test_exact_entry_boundary_reports_only_unvisited_structure(cap, layout):
    root, child = "a" * 40, "b" * 40
    entries = [dict(path=f"{i}.py", mode="100644", type="blob", sha="c" * 40) for i in range(cap)]
    if layout == "queued":
        entries[-1] = dict(path="src", mode="040000", type="tree", sha=child)
    if layout == "overflow":
        entries.append(dict(path="extra.py", mode="100644", type="blob", sha="d" * 40))
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.path.endswith(root)
        return httpx.Response(200, json=dict(sha=root, truncated=False, tree=entries))

    config = Settings(_env_file=None, director_prepare_max_entries=cap)
    scope = EvidenceScope(str(UUID(int=1)), 123, "owner/sample", "e" * 40, frozenset())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        reader = EvidenceReader(
            http,
            "owner/sample",
            max_requests=10,
            max_response_bytes=131072,
            max_total_bytes=131072,
            timeout_seconds=1,
        )
        files, limitations = await _structure(reader, root, scope, config)
    assert len(requests) == 1
    assert len(files) == cap - (layout == "queued")
    assert len(limitations) == (layout != "flat")
    assert not limitations or "상한" in limitations[0]


def _blob(path):
    return dict(path=path, mode="100644", type="blob", sha="f" * 40)


def _tree(path, sha):
    return dict(path=path, mode="040000", type="tree", sha=sha)


async def _enumerate(trees, *, max_requests, **limits):
    requested = []

    def handle(request):
        sha = request.url.path.rsplit("/", 1)[-1]
        requested.append(sha)
        return httpx.Response(200, json=dict(sha=sha, truncated=False, tree=trees[sha]))

    config = Settings(_env_file=None, **limits)
    scope = EvidenceScope(str(UUID(int=1)), 123, "owner/sample", "e" * 40, frozenset())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        reader = EvidenceReader(
            http,
            "owner/sample",
            max_requests=max_requests,
            max_response_bytes=131072,
            max_total_bytes=131072,
            timeout_seconds=1,
        )
        files, limitations = await _structure(reader, "a" * 40, scope, config)
    return requested, files, limitations


async def test_depth_cap_stops_descent_and_reports_unvisited_subtree():
    root, src, deep = "a" * 40, "b" * 40, "c" * 40
    trees = {
        root: [_blob("root.py"), _tree("src", src)],
        src: [_blob("mid.py"), _tree("deep", deep)],
        deep: [_blob("hidden.py")],
    }
    requested, files, limitations = await _enumerate(
        trees, max_requests=10, director_prepare_max_depth=1
    )
    # 상한 밖 하위 tree는 요청하지 않고, 그 안의 파일을 후보로 만들지 않는다.
    assert requested == [root, src]
    assert files == ("root.py", "src/mid.py")
    assert len(limitations) == 1 and "깊이 상한" in limitations[0]


async def test_request_budget_stops_enumeration_with_partial_candidates():
    root, first, second = "a" * 40, "b" * 40, "c" * 40
    trees = {
        root: [_blob("root.py"), _tree("first", first), _tree("second", second)],
        first: [_blob("one.py")],
        second: [_blob("two.py")],
    }
    requested, files, limitations = await _enumerate(trees, max_requests=2)
    # 예산을 넘는 요청은 보내지 않으며 이미 확인한 후보만 전체가 아님을 표시해 넘긴다.
    assert requested == [root, first]
    assert files == ("root.py", "first/one.py")
    assert len(limitations) == 1 and "요청 또는 바이트 상한" in limitations[0]


async def test_request_budget_without_candidates_fails_instead_of_empty_success():
    root, child = "a" * 40, "b" * 40
    trees = {root: [_tree("src", child)], child: [_blob("main.py")]}
    with pytest.raises(EvidenceReadError) as error:
        await _enumerate(trees, max_requests=1)
    assert error.value.code == "evidence_budget_exhausted"


async def test_oversized_and_non_regular_entries_are_skipped_with_limitations():
    root = "a" * 40
    trees = {
        root: [
            _blob("main.py"),
            dict(_blob("data.json"), size=101),
            dict(_blob("run.sh"), mode="100755", size=100),
            dict(_blob("link"), mode="120000"),
            dict(path="vendor", mode="160000", type="commit", sha="d" * 40),
        ]
    }
    _, files, limitations = await _enumerate(
        trees, max_requests=10, director_prepare_max_file_bytes=100
    )
    # 크기 상한을 넘는 파일과 일반 파일이 아닌 항목은 후보에서 빼고 이유를 남긴다.
    assert files == ("main.py", "run.sh")
    assert limitations == [
        "파일 크기 상한으로 원문을 읽지 않았습니다: data.json",
        "일반 파일이 아닌 항목은 읽지 않았습니다: link",
        "일반 파일이 아닌 항목은 읽지 않았습니다: vendor",
    ]


async def test_entry_cap_reads_source_before_vendor_and_docs():
    root = "a" * 40
    entries = [
        _tree("node_modules", "1" * 40),
        _blob("LICENSE"),
        _tree("docs", "2" * 40),
        _blob("README.md"),
        _blob("main.py"),
        _tree("src", "3" * 40),
    ]

    def handle(request):
        return httpx.Response(200, json=dict(sha=root, truncated=False, tree=entries))

    config = Settings(_env_file=None, director_prepare_max_entries=3)
    scope = EvidenceScope(str(UUID(int=1)), 123, "owner/sample", "e" * 40, frozenset())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        reader = EvidenceReader(
            http,
            "owner/sample",
            max_requests=10,
            max_response_bytes=131072,
            max_total_bytes=131072,
            timeout_seconds=1,
        )
        files, limitations = await _structure(reader, root, scope, config)
    # 상한 3개를 소스 파일·소스 디렉터리·일반 디렉터리가 차지해 의존성 디렉터리는 읽지 않는다.
    assert files == ("main.py",)
    assert limitations and "상한" in limitations[0]
