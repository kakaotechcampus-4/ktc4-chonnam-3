"""항목 수가 정확히 상한이어도 미방문 디렉터리가 있으면 한계를 전달한다."""

from uuid import UUID

import httpx
import pytest

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.features.interview.repository_sources import _structure
from app.integrations.github.evidence import EvidenceReader


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
