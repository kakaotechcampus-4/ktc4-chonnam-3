"""준비 구조·선정 모델·진행 중 근거 조회의 예산을 서로 침범하지 않는다."""

import asyncio
import base64
import hashlib
import json

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

REF, ROOT = "a" * 40, "b" * 40
REPOSITORY_ID = "00000000-0000-0000-0000-000000000001"
TEXT = "class Implementation {}\n"
BLOB = hashlib.sha1(f"blob {len(TEXT.encode())}\0".encode() + TEXT.encode()).hexdigest()
SOURCE = "components/core/runtime/service/Implementation.java"
TEST = "components/core/tests/ImplementationTest.java"


def config(**updates):
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=0.7,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=131072,
    ).model_copy(update=updates)


def shallow():
    return c.ShallowRepoAnalysis(
        REPOSITORY_ID,
        REF,
        "서비스",
        ("요청 처리",),
        ("backend",),
        ("Java",),
        "요청을 처리하는 프로젝트",
        (c.ShallowBasis("readme", "서비스"),),
        (),
    )


def model_response(data):
    return httpx.Response(
        200,
        json={
            "id": "fixture",
            "model": "fixture",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(data)}],
                }
            ],
            "usage": {"input_tokens": 8, "output_tokens": 6},
        },
    )


class Repository:
    def __init__(self, *, large_tree=False, model_delay=0, source_delay=0):
        self.model_delay, self.source_delay = model_delay, source_delay
        self.requests, self.model_inputs = [], []
        self.rows = []
        self.parents = {"": ROOT}
        for path in (SOURCE, TEST):
            parts = path.split("/")
            for length in range(1, len(parts)):
                parent = "/".join(parts[:length])
                if parent not in self.parents:
                    self.parents[parent] = hashlib.sha1(parent.encode()).hexdigest()
                    self.rows.append(
                        dict(path=parent, mode="040000", type="tree", sha=self.parents[parent])
                    )
            self.rows.append(
                dict(path=path, mode="100644", type="blob", sha=BLOB, size=len(TEXT.encode()))
            )
        if large_tree:
            self.parents["assets"] = "d" * 40
            self.rows.append(dict(path="assets", mode="040000", type="tree", sha="d" * 40))
            self.rows.extend(
                dict(
                    path=f"assets/{i:04d}-{'public-information-' * 2}.md",
                    mode="100644",
                    type="blob",
                    sha=BLOB,
                )
                for i in range(1000)
            )

    async def __call__(self, request):
        self.requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            self.model_inputs.append(json.loads(body["input"][0]["content"][0]["text"]))
            await asyncio.sleep(self.model_delay)
            return model_response(dict(selected_paths=[SOURCE, TEST]))
        if request.url.path.endswith("/sample"):
            return httpx.Response(200, json=dict(id=123, private=False))
        if "/git/commits/" in request.url.path:
            return httpx.Response(200, json=dict(sha=REF, tree=dict(sha=ROOT)))
        if "/git/trees/" in request.url.path:
            sha = request.url.path.rsplit("/", 1)[-1]
            if request.url.params.get("recursive") == "1":
                rows = self.rows
            else:
                parent = next(path for path, value in self.parents.items() if value == sha)
                rows = [
                    dict(row, path=row["path"].rsplit("/", 1)[-1])
                    for row in self.rows
                    if row["path"].rpartition("/")[0] == parent
                ]
            return httpx.Response(200, json=dict(sha=sha, truncated=False, tree=rows))
        if "/contents/" in request.url.path:
            await asyncio.sleep(self.source_delay)
            path = request.url.path.split("/contents/", 1)[1]
            assert request.url.params["ref"] == REF
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path=path,
                    sha=BLOB,
                    size=len(TEXT.encode()),
                    encoding="base64",
                    content=base64.b64encode(TEXT.encode()).decode(),
                ),
            )
        raise AssertionError("예상하지 않은 fixture 경로")


async def collect(transport, settings, **options):
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        return await collect_repository_sources(
            scope=EvidenceScope(REPOSITORY_ID, 123, "owner/sample", REF, frozenset()),
            shallow=shallow(),
            prompt=c.PromptSpec("repo_deep", "v2", "fixture", "fixture"),
            settings=settings,
            http_client=http,
            budget=CallBudget(),
            **options,
        )


async def test_large_tree_reaches_module_sources_without_using_followup_evidence_budget():
    transport = Repository(large_tree=True)
    tree_bytes = len(
        httpx.Response(200, json=dict(sha=ROOT, truncated=False, tree=transport.rows)).content
    )
    assert 131072 < tree_bytes < 524288
    settings = config(director_evidence_max_response_bytes=16, director_evidence_max_total_bytes=32)
    result = await collect(transport, settings)
    assert [source.path for source in result.item.sources] == [SOURCE, TEST]
    candidates = {row["path"] for row in transport.model_inputs[0]["candidates"]}
    assert {SOURCE, TEST}.issubset(candidates)
    assert not result.limitations
    assert len(transport.model_inputs) == 1
    assert sum(request.method == "GET" for request in transport.requests) == 6
    assert settings.director_prepare_max_response_bytes == 2097152
    assert settings.director_prepare_max_total_bytes == 8388608
    assert settings.director_prepare_max_source_bytes == 262144
    assert settings.director_prepare_max_entries == 8192
    assert settings.director_prepare_max_requests == 32


async def test_model_selection_wait_does_not_consume_source_http_deadline():
    transport = Repository(model_delay=0.3)
    result = await collect(
        transport,
        config(
            director_prepare_timeout_seconds=0.15,
            llm_timeout_seconds=0.05,
            llm_task_timeouts={"repo_deep": 1},
        ),
    )
    assert [source.path for source in result.item.sources] == [SOURCE, TEST]
    assert len(transport.model_inputs) == 1
    assert len(result.attempts) == 1


async def test_complete_inventory_survives_the_bounded_model_window():
    transport = Repository(large_tree=True)
    result = await collect(transport, config(llm_max_input_bytes=4500))
    assert len(result.inventory_paths) == 1002
    assert 0 < len(result.selection_paths) < len(result.inventory_paths)
    assert set(result.selection_paths).issubset(result.inventory_paths)
    assert {SOURCE, TEST}.issubset(result.selection_paths)
    assert len(result.candidate_paths) <= 16
    assert [row["path"] for row in transport.model_inputs[0]["candidates"]] == list(
        result.selection_paths
    )
    assert any("모델 입력 상한" in note for note in result.limitations)
    assert not result.inventory_limitations


async def test_inventory_path_not_in_model_window_is_still_rejected():
    transport = Repository(large_tree=True)
    excluded = transport.rows[-1]["path"]

    async def handle(request):
        result = await transport(request)
        return (
            model_response(dict(selected_paths=[excluded])) if request.method == "POST" else result
        )

    with pytest.raises(SourcePreparationError, match="l2_source_selection_failed") as raised:
        await collect(handle, config(llm_max_input_bytes=4500))
    assert raised.value.failure.stage == "semantic"
    assert len(transport.model_inputs) == 1


async def test_request_overhead_failure_does_not_spend_a_provider_attempt():
    transport = Repository()
    with pytest.raises(
        SourcePreparationError, match="repository_selection_input_too_large"
    ) as raised:
        await collect(transport, config(llm_max_input_bytes=100))
    assert raised.value.failure.stage == "budget"
    assert raised.value.attempts == () and transport.model_inputs == []


async def test_whitespace_overlap_keeps_other_selected_files(monkeypatch):
    text = "alpha\n\nbeta\n"
    digest = hashlib.sha1(f"blob {len(text.encode())}\0".encode() + text.encode()).hexdigest()
    monkeypatch.setattr(__name__ + ".TEXT", text)
    monkeypatch.setattr(__name__ + ".BLOB", digest)
    transport = Repository()
    result = await collect(
        transport, config(director_prepare_max_source_bytes=16), paths=(SOURCE, TEST)
    )
    assert {source.path for source in result.item.sources} == {SOURCE, TEST}
    assert all(source.content.strip() for source in result.item.sources)
    assert sum(len(source.content.encode()) for source in result.item.sources) <= 16
    assert any("공백" in note and SOURCE in note for note in result.limitations)
    assert all(source.start_line == 1 and source.end_line == 2 for source in result.item.sources)
    assert transport.model_inputs == []


async def test_cached_paths_do_not_gain_model_time_as_extra_network_budget():
    transport = Repository(source_delay=0.3)
    with pytest.raises(SourcePreparationError, match="repository_source_timeout"):
        await collect(transport, config(director_prepare_timeout_seconds=0.15), paths=(SOURCE,))
    assert transport.model_inputs == []


async def test_network_deadline_still_limits_source_reads_after_slow_selection():
    transport = Repository(model_delay=0.3, source_delay=0.3)
    with pytest.raises(SourcePreparationError, match="repository_source_timeout"):
        await collect(transport, config(director_prepare_timeout_seconds=0.15))
    assert len(transport.model_inputs) == 1
