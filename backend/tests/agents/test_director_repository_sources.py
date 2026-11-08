"""원문 수집기의 구조 상한과 부분 실패를 실행 계층 없이 검증한다."""

import asyncio
import base64
import hashlib
import json

import httpx
import pytest
from devon_ai import contracts as c

from app.core.config import Settings

TEXT = "class Service:\n    pass\n"


BLOB = hashlib.sha1(f"blob {len(TEXT.encode())}\0".encode() + TEXT.encode()).hexdigest()


TREE = "c" * 40


PATH = "서비스 code.py"


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=131072,
        llm_max_response_bytes=131072,
    )


def shallow(seed):
    return c.ShallowRepoAnalysis(
        str(seed["repo_id"]),
        seed["sha"],
        "서비스",
        ("요청 처리",),
        ("backend",),
        ("Python",),
        "요청을 처리하는 프로젝트",
        (c.ShallowBasis("readme", "서비스"),),
        (),
    )


class Transport:
    def __init__(self, seed, *, miss=False):
        self.seed = seed
        self.model_operations = []
        self.model_payloads = []
        self.github = []
        self.outputs = [dict(selected_paths=[PATH])] if miss else []

    async def __call__(self, request):
        if request.method == "POST":
            body = json.loads(request.content)
            payload = json.loads(body["input"][0]["content"][0]["text"])
            self.model_operations.append(payload.get("operation", "analyze"))
            self.model_payloads.append(payload)
            return response(self.outputs.pop(0))
        self.github.append(request)
        suffix = request.url.path.removeprefix("/repos/owner/sample")
        if not suffix:
            return httpx.Response(200, json=dict(id=123, private=False))
        if suffix == f"/git/commits/{self.seed['sha']}":
            return httpx.Response(200, json=dict(sha=self.seed["sha"], tree=dict(sha=TREE)))
        if suffix == f"/git/trees/{TREE}":
            return httpx.Response(
                200,
                json=dict(
                    sha=TREE,
                    truncated=False,
                    tree=[
                        dict(
                            path=PATH,
                            mode="100644",
                            type="blob",
                            sha=BLOB,
                        )
                    ],
                ),
            )
        if suffix == f"/contents/{PATH}":
            assert request.url.params["ref"] == self.seed["sha"]
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path=PATH,
                    sha=BLOB,
                    size=len(TEXT.encode()),
                    encoding="base64",
                    content=base64.b64encode(TEXT.encode()).decode(),
                ),
            )
        raise AssertionError(f"예상하지 않은 GitHub 경로: {suffix}")


async def test_source_structure_is_bounded_and_keeps_unread_scope_limitations():
    from uuid import UUID

    from app.agents.director.tools import EvidenceScope
    from app.features.interview.repository_sources import collect_repository_sources
    from app.integrations.llm.client import CallBudget

    seed = dict(repo_id=UUID(int=1), sha="a" * 40)
    transport = Transport(seed, miss=True)

    async def extra_tree(request):
        response = await transport(request)
        if "/git/trees/" in request.url.path:
            value = response.json()
            value["tree"].append(dict(path="unread.py", mode="100644", type="blob", sha=BLOB))
            return httpx.Response(200, json=value)
        return response

    config = settings().model_copy(update={"director_prepare_max_entries": 1})
    async with httpx.AsyncClient(transport=httpx.MockTransport(extra_tree)) as http:
        result = await collect_repository_sources(
            scope=EvidenceScope(
                str(seed["repo_id"]), 123, "owner/sample", seed["sha"], frozenset()
            ),
            shallow=shallow(seed),
            prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
            settings=config,
            http_client=http,
            budget=CallBudget(),
        )
    assert [source.path for source in result.item.sources] == [PATH]
    assert any("상한" in note for note in result.limitations)
    assert all("recursive" not in request.url.params for request in transport.github)
    assert transport.model_operations == ["select"]


@pytest.mark.parametrize("failure", ["binary", "timeout"])
async def test_failed_second_file_keeps_verified_first_source_and_error_scope(failure):
    from uuid import UUID

    from app.agents.director.tools import EvidenceScope
    from app.features.interview.repository_sources import collect_repository_sources
    from app.integrations.llm.client import CallBudget

    seed = dict(repo_id=UUID(int=1), sha="a" * 40)
    transport = Transport(seed)
    binary = b"\0binary"
    digest = hashlib.sha1(f"blob {len(binary)}\0".encode() + binary).hexdigest()

    async def partial(request):
        if request.url.path.endswith("/contents/binary.dat"):
            if failure == "timeout":
                await asyncio.Event().wait()
            return httpx.Response(
                200,
                json=dict(
                    type="file",
                    path="binary.dat",
                    sha=digest,
                    encoding="base64",
                    size=len(binary),
                    content=base64.b64encode(binary).decode(),
                ),
            )
        response = await transport(request)
        if "/git/trees/" in request.url.path:
            value = response.json()
            value["tree"].append(dict(path="binary.dat", mode="100644", type="blob", sha=digest))
            return httpx.Response(200, json=value)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(partial)) as http:
        result = await collect_repository_sources(
            scope=EvidenceScope(
                str(seed["repo_id"]), 123, "owner/sample", seed["sha"], frozenset()
            ),
            shallow=shallow(seed),
            prompt=c.PromptSpec("repo_deep", "v1", "fixture", "fixture"),
            settings=settings().model_copy(update={"director_prepare_timeout_seconds": 0.1}),
            http_client=http,
            budget=CallBudget(),
            paths=(PATH, "binary.dat"),
        )
    assert result.item.sources == (c.SourceDocument(PATH, "file", TEXT, "entire file"),)
    if failure == "binary":
        assert any(
            "binary.dat" in note and "evidence_not_text" in note for note in result.limitations
        )
    else:
        assert any("시간" in note for note in result.limitations)
    assert transport.model_operations == []


def response(data, model="fixture-model"):
    raw = json.dumps(data, ensure_ascii=False)
    return httpx.Response(
        200,
        json={
            "id": "fixture",
            "model": model,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": raw}],
                }
            ],
            "usage": {"input_tokens": 8, "output_tokens": 6},
        },
    )
