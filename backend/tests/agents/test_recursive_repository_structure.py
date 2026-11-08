"""고정 tree의 제한된 재귀 목록으로 임의의 깊은 모듈을 찾아 원문 예산을 남긴다."""

import base64
import hashlib

import httpx
import pytest

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.features.interview.repository_sources import _structure
from app.integrations.github.evidence import EvidenceReader, EvidenceReadError

ROOT = "a" * 40
TEXT = "actual original\n"
BLOB = hashlib.sha1(f"blob {len(TEXT.encode())}\0".encode() + TEXT.encode()).hexdigest()


class Trees:
    def __init__(self, *, truncated=False, oversized=False):
        self.rows = []
        self.parents = {"": ROOT}
        self.seen = []
        self.truncated, self.oversized = truncated, oversized
        for depth in range(7):
            path = "/".join(f"arbitrary{i}" for i in range(depth + 1))
            sha = hashlib.sha1(path.encode()).hexdigest()
            self.rows.append(dict(path=path, sha=sha, type="tree", mode="040000"))
            self.parents[path] = sha
        self.path = path + "/implementation.custom"
        self.rows.append(dict(path=self.path, sha=BLOB, type="blob", mode="100644", size=len(TEXT)))
        self.rows.append(
            dict(path="info.txt", sha=BLOB, type="blob", mode="100644", size=len(TEXT))
        )

    async def __call__(self, request):
        self.seen.append(request)
        sha = request.url.path.rsplit("/", 1)[-1]
        if "/git/trees/" in request.url.path:
            if request.url.params.get("recursive") == "1":
                if self.oversized:
                    return httpx.Response(
                        200, headers={"Content-Length": "999999"}, content=b"unused"
                    )
                return httpx.Response(
                    200, json=dict(sha=ROOT, truncated=self.truncated, tree=self.rows)
                )
            parent = next(path for path, value in self.parents.items() if value == sha)
            entries = [
                dict(row, path=row["path"].rsplit("/", 1)[-1])
                for row in self.rows
                if row["path"].rpartition("/")[0] == parent
            ]
            return httpx.Response(200, json=dict(sha=sha, truncated=False, tree=entries))
        if "/contents/" in request.url.path:
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path=self.path,
                    sha=BLOB,
                    encoding="base64",
                    size=len(TEXT),
                    content=base64.b64encode(TEXT.encode()).decode(),
                ),
            )
        raise AssertionError("Unexpected fixture route")


async def run(trees, *, entries=512, depth=8):
    async with httpx.AsyncClient(transport=httpx.MockTransport(trees)) as http:
        reader = EvidenceReader(
            http,
            "owner/repo",
            max_requests=5,
            max_response_bytes=16384,
            max_total_bytes=65536,
            timeout_seconds=2,
        )
        try:
            files, limitations = await _structure(
                reader,
                ROOT,
                EvidenceScope("repo", 1, "owner/repo", "b" * 40, frozenset()),
                Settings(_env_file=None).model_copy(
                    update={
                        "director_prepare_max_entries": entries,
                        "director_prepare_max_depth": depth,
                    }
                ),
                reserve_requests=1,
                reserve_bytes=16384,
            )
        except EvidenceReadError:
            files, limitations = (), ["old_bounded_walk_cannot_reach_deep_source"]
        if trees.path in files and not trees.truncated:
            blob = await reader.regular_blob(ROOT, trees.path)
            original = await reader.file_text(trees.path, "b" * 40, blob)
            assert original == TEXT
        return files, limitations, reader


async def test_deep_nonstandard_module_is_listed_and_verified_in_three_requests():
    trees = Trees()
    files, limitations, reader = await run(trees)
    assert trees.path in files
    assert not limitations
    assert len(trees.seen) == 3
    assert sum(request.url.params.get("recursive") == "1" for request in trees.seen) == 1
    assert reader.requests_left == 2


async def test_depth_and_entry_caps_are_not_bypassed_by_recursive_listing():
    trees = Trees()
    files, limitations, _ = await run(trees, depth=2)
    assert trees.path not in files and any("깊이" in item for item in limitations)
    files, limitations, _ = await run(Trees(), entries=3)
    assert trees.path not in files and any("항목" in item for item in limitations)


async def test_truncated_index_keeps_unknown_scope_and_never_caches_incomplete_parents():
    trees = Trees(truncated=True)
    files, limitations, reader = await run(trees)
    assert files and any("생략" in item for item in limitations)
    assert trees.parents["arbitrary0"] not in reader.trees


async def test_oversized_recursive_response_falls_back_without_spending_source_reserve():
    trees = Trees(oversized=True)
    files, limitations, reader = await run(trees)
    assert "info.txt" in files
    assert limitations and reader.bytes_left >= 16384


async def test_identical_subtree_reused_by_two_modules_does_not_duplicate_parent_entries():
    trees = Trees()
    trees.rows.extend(
        dict(row, path="copy" + row["path"][len("arbitrary0") :])
        for row in list(trees.rows)
        if row["path"].startswith("arbitrary0")
    )
    files, limitations, _ = await run(trees)
    assert trees.path in files and not limitations


@pytest.mark.parametrize("change", ["traversal", "duplicate", "missing_parent", "mode_type", "sha"])
async def test_invalid_recursive_metadata_is_rejected_before_cache_publish(change):
    from app.features.interview.repository_structure import recursive_files

    trees = Trees()
    if change == "traversal":
        trees.rows[-1]["path"] = "../private"
    elif change == "duplicate":
        trees.rows.append(dict(trees.rows[-1]))
    elif change == "missing_parent":
        trees.rows[0]["mode"] = "120000"
    elif change == "mode_type":
        trees.rows[-1]["mode"] = {}
    else:
        trees.rows[-1]["sha"] = "not_a_sha"
    async with httpx.AsyncClient(transport=httpx.MockTransport(trees)) as http:
        reader = EvidenceReader(
            http,
            "owner/repo",
            max_requests=5,
            max_response_bytes=16384,
            max_total_bytes=65536,
            timeout_seconds=2,
        )
        with pytest.raises(EvidenceReadError):
            await recursive_files(
                reader,
                ROOT,
                EvidenceScope("repo", 1, "owner/repo", "b" * 40, frozenset()),
                Settings(_env_file=None),
                max_bytes=16384,
            )
        assert reader.trees == {}
