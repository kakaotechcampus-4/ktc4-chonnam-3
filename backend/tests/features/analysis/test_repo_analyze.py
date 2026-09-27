"""L0-b/L1 연결의 캐시·실패 보존과 run별 결과 참조를 검증한다."""

import asyncio
import base64
import importlib
import json
import uuid

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import event, select, update

from app.core.config import LLMSettings
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.knowledge import PromptVersion
from app.db.models.user import GithubAccount, User

SHA = "a" * 40


def _bound_rows():
    repository_id = uuid.uuid4()
    analysis = RepoAnalysis(
        id=uuid.uuid4(),
        repository_id=repository_id,
        analysis_level="l1",
        head_sha=SHA,
        prompt_version="repo_shallow_v1",
        model="test-model",
        status="succeeded",
        error_code=None,
        tech_stack=["Python"],
    )
    candidate = AnalysisRepoCandidate(
        id=uuid.uuid4(),
        analysis_job_id=uuid.uuid4(),
        repository_id=repository_id,
        base_rank=1,
        filter_status="eligible",
        ranking_signals={
            "preserved": 3,
            "analysis": {
                "analysis_id": str(analysis.id),
                "head_sha": SHA,
                "prompt_version": "repo_shallow_v1",
                "status": "succeeded",
                "error_code": None,
            },
        },
    )
    return candidate, analysis


def test_resolves_only_the_analysis_bound_to_this_run():
    results = importlib.import_module("app.features.analysis.analysis_results")
    candidate, analysis = _bound_rows()
    newer = RepoAnalysis(id=uuid.uuid4(), repository_id=analysis.repository_id)
    assert (
        results.resolve_bound_analysis(candidate, {analysis.id: analysis, newer.id: newer})
        is analysis
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_id", uuid.UUID(int=0)),
        ("analysis_level", "l2"),
        ("head_sha", "b" * 40),
        ("prompt_version", "repo_shallow_v2"),
        ("status", "failed"),
        ("id", uuid.UUID(int=0)),
    ],
)
def test_rejects_mismatched_bound_analysis(field, value):
    results = importlib.import_module("app.features.analysis.analysis_results")
    candidate, analysis = _bound_rows()
    original_id = analysis.id
    setattr(analysis, field, value)
    assert results.resolve_bound_analysis(candidate, {original_id: analysis}) is None


@pytest.mark.parametrize("status", ["failed", "partial"])
def test_failed_run_does_not_inherit_a_later_cached_success(status):
    results = importlib.import_module("app.features.analysis.analysis_results")
    candidate, analysis = _bound_rows()
    candidate.ranking_signals["analysis"]["status"] = status
    candidate.ranking_signals["analysis"]["error_code"] = "llm_timeout"
    assert results.resolve_bound_analysis(candidate, {analysis.id: analysis}) is None


@pytest.mark.parametrize(
    "snapshot", [None, {}, "invalid", {"analysis_id": "not-a-uuid", "status": "succeeded"}]
)
def test_missing_or_invalid_snapshot_is_not_replaced_by_latest_analysis(snapshot):
    results = importlib.import_module("app.features.analysis.analysis_results")
    candidate, analysis = _bound_rows()
    candidate.ranking_signals = {"analysis": snapshot}
    assert results.resolve_bound_analysis(candidate, {analysis.id: analysis}) is None


SETTINGS = LLMSettings(
    openai_api_key=SecretStr("fixture-key"),
    llm_default_model="configured-model",
    llm_timeout_seconds=2,
    llm_max_output_tokens=1024,
    llm_max_input_bytes=65536,
    llm_max_response_bytes=65536,
)


async def _seed(sessions, *, count=1):
    async with sessions.begin() as session:
        user = User(name="Fixture")
        session.add(user)
        await session.flush()
        session.add(
            GithubAccount(
                user_id=user.id, github_user_id=1, login="owner", access_token_encrypted=b"fixture"
            )
        )
        run = AnalysisJob(user_id=user.id, job_type="analysis_run", status="succeeded")
        session.add(run)
        session.add(
            PromptVersion(
                task_name="repo_shallow",
                version="repo_shallow_v1",
                model="configured-model",
                template="fixture prompt",
                is_active=True,
            )
        )
        repos = [
            Repository(
                user_id=user.id,
                github_repo_id=n + 1,
                name=f"repo{n}",
                full_name=f"owner/repo{n}",
                default_branch="main",
                primary_language="Python",
                description="service",
            )
            for n in range(count)
        ]
        session.add_all(repos)
        await session.flush()
        session.add_all(
            [
                AnalysisRepoCandidate(
                    analysis_job_id=run.id,
                    repository_id=repo.id,
                    base_rank=n + 1,
                    batch_no=1,
                    batch_rank=n + 1,
                    filter_status="eligible",
                    ranking_signals={"existing": "kept"},
                )
                for n, repo in enumerate(repos)
            ]
        )
        return run.id, [repo.id for repo in repos]


async def _another_run(sessions, original_run, repo_id):
    async with sessions.begin() as session:
        old = await session.get(AnalysisJob, original_run)
        run = AnalysisJob(user_id=old.user_id, job_type="analysis_run", status="succeeded")
        session.add(run)
        await session.flush()
        session.add(
            AnalysisRepoCandidate(
                analysis_job_id=run.id,
                repository_id=repo_id,
                base_rank=1,
                batch_no=1,
                batch_rank=1,
                filter_status="eligible",
            )
        )
        return run.id


def _github_reply(
    request, *, sha=SHA, missing_readme=False, inaccessible=False, unauthorized=False
):
    if unauthorized:
        return httpx.Response(401, json={"message": "Bad credentials"})
    if inaccessible:
        return httpx.Response(404, json={"message": "Not Found"})
    path = request.url.path
    if path.endswith("/languages"):
        return httpx.Response(200, json={"Python": 100})
    if path.endswith("/readme"):
        if missing_readme:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"Python service README").decode(),
            },
        )
    if path.endswith("/commits/main"):
        return httpx.Response(200, json={"sha": sha})
    if path.endswith("/commits"):
        return httpx.Response(200, json=[{"sha": sha}])
    raise AssertionError(path)


def _model_reply(repo_ids, sha=SHA, *, invalid_tech=None):
    items = [
        {
            "repository_id": str(repo_id),
            "head_sha": sha,
            "purpose": "service",
            "key_features": ["query"],
            "project_types": ["backend"],
            "tech_stack": [
                invalid_tech if invalid_tech is not None and repo_id == repo_ids[0] else "Python"
            ],
            "project_role_summary": "service project",
            "basis": [{"kind": "languages", "claim": "Python source"}],
            "limitations": ["runtime unverified"],
        }
        for repo_id in repo_ids
    ]
    raw = json.dumps({"repositories": items})
    return httpx.Response(
        200,
        json={
            "id": "fixture",
            "model": "actual-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": raw}],
                }
            ],
            "usage": {"input_tokens": 20, "output_tokens": 30},
        },
    )


async def _run(sessions, run_id, handler, *, batch_no=1, **kwargs):
    from app.features.analysis.pipeline.steps.repo_analyze import analyze_candidate_batch
    from app.integrations.github.client import GithubClient

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await analyze_candidate_batch(
            sessions,
            run_id,
            batch_no,
            github_client=GithubClient("fixture-token", client=http),
            github_token_encrypted=b"fixture",
            login="owner",
            settings=SETTINGS,
            http_client=http,
            **kwargs,
        )


async def _read(sessions, run_id):
    async with sessions() as session:
        candidates = list(
            (
                await session.scalars(
                    select(AnalysisRepoCandidate)
                    .where(AnalysisRepoCandidate.analysis_job_id == run_id)
                    .order_by(AnalysisRepoCandidate.base_rank)
                )
            ).all()
        )
        analyses = list((await session.scalars(select(RepoAnalysis))).all())
        repos = list(
            (await session.scalars(select(Repository).order_by(Repository.github_repo_id))).all()
        )
        return candidates, analyses, repos
