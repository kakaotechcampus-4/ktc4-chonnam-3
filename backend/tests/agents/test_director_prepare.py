"""실제 PostgreSQL과 고정 GitHub 원문으로 준비부터 첫 Director 질문까지 검증한다."""

import asyncio
import base64
import hashlib
import importlib
import json
from dataclasses import asdict

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select, update

from app.core.config import Settings
from app.db.models import (
    AnalysisRepoCandidate,
    Evidence,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    PromptVersion,
    RepoAnalysis,
    Repository,
    ScoreCriterion,
    SessionRepository,
)
from app.db.models.report import SCORE_KEYS

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


def prepare():
    function = getattr(
        importlib.import_module("app.features.interview.prepare"), "prepare_interview", None
    )
    assert callable(function), "실제 준비 실행 함수가 필요하다"
    return function


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


def area():
    return dict(path=PATH, observation="서비스 클래스", scope="entire file", limitations=[])


def deep(seed):
    return dict(
        repository_id=str(seed["repo_id"]),
        head_sha=seed["sha"],
        architecture_summary="서비스 클래스",
        confirmed_technologies=["Python"],
        notable_areas=[area()],
        limitations=[],
    )


def plan():
    return dict(
        question=dict(
            persona="hr_manager",
            text="프로젝트에서 맡은 역할을 소개해 주세요.",
            topic_code="role",
            question_contract=dict(
                purpose="본인 역할 소개",
                required_points=[dict(key="role", description="본인 역할")],
                assumptions=[],
                basis_refs=[],
                evaluation_scope="역할",
            ),
            evidence_refs=[],
            jd_requirement_ids=[],
        ),
        intent="역할 확인",
        reason_summary="첫 자기소개",
    )


REVIEW = dict(
    plan_valid=True,
    context_valid=True,
    wording_valid=True,
    contract_matches=True,
    safe_alternative=True,
    reason_summary="원문에 맞는 질문",
)


def response(data):
    return httpx.Response(
        200,
        json=dict(
            id="fixture",
            model="actual-fixture",
            status="completed",
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[dict(type="output_text", text=json.dumps(data, ensure_ascii=False))],
                )
            ],
        ),
    )


class Transport:
    def __init__(self, seed, *, miss=False):
        self.seed = seed
        self.model_operations = []
        self.model_payloads = []
        self.github = []
        self.outputs = [dict(selected_paths=[PATH]), deep(seed)] if miss else []
        self.outputs += [plan(), REVIEW]

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


@pytest.fixture
async def ready(agent_sessions, agent_seed):
    async with agent_sessions.begin() as db:
        await db.execute(update(InterviewSession).values(status="preparing"))
        await db.execute(update(Repository).values(head_sha="b" * 40))
        l1 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l1"))
        l1.result = asdict(shallow(agent_seed))
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        db.add(
            AnalysisRepoCandidate(
                analysis_job_id=interview.analysis_job_id,
                repository_id=agent_seed["repo_id"],
                base_rank=1,
                batch_no=1,
                batch_rank=1,
                filter_status="eligible",
                ranking_signals={
                    "analysis": dict(
                        analysis_id=str(l1.id),
                        status="succeeded",
                        head_sha=l1.head_sha,
                        prompt_version=l1.prompt_version,
                    )
                },
            )
        )
        l2 = await db.scalar(select(RepoAnalysis).where(RepoAnalysis.analysis_level == "l2"))
        l2.prompt_version = "repo_deep_v1"
        l2.notable_areas = [area()]
        l2.result = dict(analysis=deep(agent_seed), rejected_areas=[])
        for task in ("repo_deep", "answer_analysis"):
            db.add(
                PromptVersion(
                    task_name=task,
                    version=f"{task}_v1",
                    model="fixture",
                    template="fixture",
                    is_active=True,
                )
            )
        for index, key in enumerate(SCORE_KEYS):
            db.add(
                ScoreCriterion(
                    score_key=key,
                    label_ko=key,
                    rubric={"verified": True},
                    display_order=index,
                    is_active=True,
                )
            )
    return agent_seed


async def run(sessions, seed, transport):
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        return await prepare()(
            sessions,
            user_id=seed["owner"],
            interview_id=seed["interview_id"],
            settings=settings(),
            http_client=http,
        )
