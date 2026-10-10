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


async def test_detail_and_l1_persist_then_cache_requires_exact_sha_and_prompt(session_factory):
    run_id, repo_ids = await _seed(session_factory)
    current_sha = SHA
    model_calls = 0
    checked_out = 0

    def checkout(*args):
        nonlocal checked_out
        checked_out += 1

    def checkin(*args):
        nonlocal checked_out
        checked_out -= 1

    engine = session_factory.kw["bind"]
    event.listen(engine.sync_engine, "checkout", checkout)
    event.listen(engine.sync_engine, "checkin", checkin)

    async def handler(request):
        nonlocal model_calls
        # 외부 I/O 중에는 앞선 DB 조회 transaction이 남아 있지 않아야 한다.
        assert checked_out == 0
        if request.url.host == "api.github.com":
            return _github_reply(request, sha=current_sha)
        model_calls += 1
        return _model_reply(repo_ids, current_sha)

    await _run(session_factory, run_id, handler)
    await _run(session_factory, run_id, handler)
    candidates, analyses, repos = await _read(session_factory, run_id)
    assert model_calls == 1
    assert len(analyses) == 1
    assert analyses[0].tech_stack == ["Python"] and analyses[0].model == "actual-model"
    assert (
        analyses[0].summary is None
        and analyses[0].result["project_role_summary"] == "service project"
    )
    assert repos[0].languages == {"Python": 100} and repos[0].head_sha == SHA
    assert repos[0].readme_text == "Python service README" and repos[0].user_commit_count == 1
    assert candidates[0].ranking_signals["existing"] == "kept"
    assert candidates[0].ranking_signals["analysis"] == {
        "analysis_id": str(analyses[0].id),
        "head_sha": SHA,
        "prompt_version": "repo_shallow_v1",
        "status": "succeeded",
        "error_code": None,
    }
    current_sha = "b" * 40
    await _run(session_factory, run_id, handler)
    async with session_factory.begin() as session:
        await session.execute(update(PromptVersion).values(is_active=False))
        session.add(
            PromptVersion(
                task_name="repo_shallow",
                version="repo_shallow_v2",
                model="configured-model",
                template="fixture prompt 2",
                is_active=True,
            )
        )
    await _run(session_factory, run_id, handler)
    candidates, analyses, _ = await _read(session_factory, run_id)
    assert model_calls == 3 and len(analyses) == 3
    assert candidates[0].ranking_signals["analysis"]["prompt_version"] == "repo_shallow_v2"


async def test_failed_cache_is_retried_without_rewriting_the_earlier_run_failure(session_factory):
    run_id, repo_ids = await _seed(session_factory)

    def fail(request):
        if request.url.host == "api.github.com":
            return _github_reply(request)
        return httpx.Response(
            400, json={"error": {"message": "fixture rejection", "type": "invalid_request_error"}}
        )

    await _run(session_factory, run_id, fail)
    old_candidates, old_analyses, _ = await _read(session_factory, run_id)
    old_snapshot = old_candidates[0].ranking_signals["analysis"].copy()
    assert old_snapshot["status"] == "failed" and old_snapshot["error_code"] == "llm_failed"
    next_run = await _another_run(session_factory, run_id, repo_ids[0])
    await _run(
        session_factory,
        next_run,
        lambda request: (
            _github_reply(request)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        ),
    )
    candidates, analyses, _ = await _read(session_factory, run_id)
    next_candidates, _, _ = await _read(session_factory, next_run)
    assert len(analyses) == 1 and analyses[0].id == old_analyses[0].id
    assert analyses[0].status == "succeeded"
    assert candidates[0].ranking_signals["analysis"] == old_snapshot
    assert next_candidates[0].ranking_signals["analysis"]["status"] == "succeeded"
    results = importlib.import_module("app.features.analysis.analysis_results")
    assert results.resolve_bound_analysis(candidates[0], {analyses[0].id: analyses[0]}) is None


@pytest.mark.parametrize("truncated", [False, True])
async def test_partial_collection_keeps_fields_and_cannot_be_selected_as_success(
    session_factory, truncated
):
    run_id, repo_ids = await _seed(session_factory)

    def handler(request):
        return (
            _github_reply(request, missing_readme=not truncated)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        )

    await _run(session_factory, run_id, handler, readme_max_chars=5 if truncated else 20000)
    candidates, analyses, repos = await _read(session_factory, run_id)
    assert analyses[0].status == "partial" and analyses[0].tech_stack == ["Python"]
    assert analyses[0].error_code == (None if truncated else "no_readme")
    assert candidates[0].ranking_signals["analysis"]["status"] == "partial"
    assert repos[0].is_accessible is True and repos[0].languages == {"Python": 100}
    assert repos[0].readme_truncated is truncated


async def test_inaccessible_repository_is_excluded_without_fabricated_l1(session_factory):
    run_id, _ = await _seed(session_factory)

    def handler(request):
        assert request.url.host == "api.github.com"
        return _github_reply(request, inaccessible=True)

    await _run(session_factory, run_id, handler)
    candidates, analyses, repos = await _read(session_factory, run_id)
    assert analyses == [] and repos[0].is_accessible is False
    assert (
        candidates[0].filter_status == "excluded" and candidates[0].filter_reason == "inaccessible"
    )
    assert candidates[0].ranking_signals["analysis"] == {
        "analysis_id": None,
        "head_sha": None,
        "prompt_version": None,
        "status": "failed",
        "error_code": "repo_unreachable",
    }


async def test_token_failure_revokes_account_and_blocks_subsequent_collection(session_factory):
    run_id, _ = await _seed(session_factory, count=2)
    requests = []

    def handler(request):
        requests.append(request)
        return _github_reply(request, unauthorized=True)

    await _run(session_factory, run_id, handler)
    await _run(session_factory, run_id, handler)
    candidates, analyses, _ = await _read(session_factory, run_id)
    async with session_factory() as session:
        account = (await session.scalars(select(GithubAccount))).one()
    assert account.token_status == "revoked" and len(requests) == 1
    assert analyses == []
    assert all(
        candidate.ranking_signals["analysis"]["error_code"] == "token_invalid"
        for candidate in candidates
    )


async def test_late_failure_cannot_overwrite_concurrent_success_or_its_binding(session_factory):
    run_id, repo_ids = await _seed(session_factory)
    waiting = asyncio.Event()
    release_failure = asyncio.Event()

    async def delayed_failure(request):
        if request.url.host == "api.github.com":
            return _github_reply(request)
        waiting.set()
        await asyncio.wait_for(release_failure.wait(), timeout=10)
        return httpx.Response(
            400, json={"error": {"message": "fixture rejection", "type": "invalid_request_error"}}
        )

    task = asyncio.create_task(_run(session_factory, run_id, delayed_failure))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=10)
        await _run(
            session_factory,
            run_id,
            lambda request: (
                _github_reply(request)
                if request.url.host == "api.github.com"
                else _model_reply(repo_ids)
            ),
        )
    finally:
        release_failure.set()
        await task
    candidates, analyses, _ = await _read(session_factory, run_id)
    assert len(analyses) == 1 and analyses[0].status == "succeeded"
    assert analyses[0].tech_stack == ["Python"] and analyses[0].raw_output is not None
    assert candidates[0].ranking_signals["analysis"]["status"] == "succeeded"


async def test_changed_snapshot_invalidates_all_run_recommendations_but_cache_noop_does_not(
    session_factory,
):
    run_id, repo_ids = await _seed(session_factory, count=2)

    def handler(request):
        return (
            _github_reply(request)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        )

    await _run(session_factory, run_id, handler)
    async with session_factory.begin() as session:
        session.add_all(
            [
                RepoMatchScore(
                    analysis_job_id=run_id,
                    repository_id=repo_id,
                    candidate_source="rule_filter",
                    score=None,
                    is_recommended=True,
                    recommend_reason="Python",
                )
                for repo_id in repo_ids
            ]
        )
    await _run(session_factory, run_id, handler)
    async with session_factory() as session:
        assert len((await session.scalars(select(RepoMatchScore))).all()) == 2

    def changed(request):
        if request.url.host == "api.github.com":
            return _github_reply(request, sha="b" * 40 if "/repo0/" in request.url.path else SHA)
        return _model_reply(repo_ids[:1], "b" * 40)

    await _run(session_factory, run_id, changed)
    async with session_factory() as session:
        assert list((await session.scalars(select(RepoMatchScore))).all()) == []


async def test_missing_active_prompt_does_not_call_llm_or_create_default_analysis(session_factory):
    from app.llm_tasks.prompt_loader import PromptNotFoundError

    run_id, _ = await _seed(session_factory)
    async with session_factory.begin() as session:
        await session.execute(update(PromptVersion).values(is_active=False))

    def handler(request):
        assert request.url.host == "api.github.com"
        return _github_reply(request)

    with pytest.raises(PromptNotFoundError):
        await _run(session_factory, run_id, handler)
    _, analyses, _ = await _read(session_factory, run_id)
    assert analyses == []


async def test_cache_miss_keeps_original_candidate_batch_position(session_factory):
    run_id, repo_ids = await _seed(session_factory, count=2)
    await _run(
        session_factory,
        run_id,
        lambda request: (
            _github_reply(request)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        ),
    )

    def changed(request):
        if request.url.host == "api.github.com":
            return _github_reply(request, sha="b" * 40 if "/repo1/" in request.url.path else SHA)
        return _model_reply(repo_ids[1:], "b" * 40)

    await _run(session_factory, run_id, changed)
    _, analyses, _ = await _read(session_factory, run_id)
    fresh = next(row for row in analyses if row.head_sha == "b" * 40)
    assert fresh.batch_position == 1


@pytest.mark.parametrize("case", ["wrong_job_type", "missing_run", "invalid_batch"])
async def test_rejects_invalid_run_or_batch_before_external_io(session_factory, case):
    from app.core.errors import AppError
    from app.shared.enums import Reason

    run_id, _ = await _seed(session_factory)
    if case == "wrong_job_type":
        async with session_factory.begin() as session:
            await session.execute(
                update(AnalysisJob).where(AnalysisJob.id == run_id).values(job_type="initial_sync")
            )
    if case == "missing_run":
        run_id = uuid.uuid4()

    def unexpected(request):
        raise AssertionError("잘못된 입력으로 외부 API를 호출함")

    with pytest.raises(AppError) as caught:
        await _run(
            session_factory, run_id, unexpected, batch_no=0 if case == "invalid_batch" else 1
        )
    assert caught.value.reason == (
        Reason.INVALID_REQUEST if case == "invalid_batch" else Reason.NOT_FOUND
    )


async def test_later_configuration_failure_does_not_rollback_token_revocation(session_factory):
    from app.llm_tasks.prompt_loader import PromptNotFoundError

    run_id, _ = await _seed(session_factory)
    async with session_factory.begin() as session:
        await session.execute(update(PromptVersion).values(is_active=False))

    def handler(request):
        assert request.url.host == "api.github.com"
        return _github_reply(request, unauthorized="author" in request.url.params)

    with pytest.raises(PromptNotFoundError):
        await _run(session_factory, run_id, handler)
    async with session_factory() as session:
        account = (await session.scalars(select(GithubAccount))).one()
        repo = (await session.scalars(select(Repository))).one()
    assert account.token_status == "revoked"
    assert repo.head_sha == SHA


async def test_accessibility_change_invalidates_matches_even_with_identical_failure_snapshot(
    session_factory,
):
    run_id, repo_ids = await _seed(session_factory)
    await _run(
        session_factory,
        run_id,
        lambda request: httpx.Response(500, json={"message": "unavailable"}),
    )
    candidates, _, repos = await _read(session_factory, run_id)
    before = candidates[0].ranking_signals["analysis"].copy()
    assert candidates[0].filter_status == "eligible" and repos[0].is_accessible
    async with session_factory.begin() as session:
        session.add(
            RepoMatchScore(
                analysis_job_id=run_id,
                repository_id=repo_ids[0],
                candidate_source="rule_filter",
                is_recommended=False,
            )
        )
    await _run(session_factory, run_id, lambda request: _github_reply(request, inaccessible=True))
    candidates, _, _ = await _read(session_factory, run_id)
    assert candidates[0].ranking_signals["analysis"] == before
    assert candidates[0].filter_status == "excluded"
    async with session_factory() as session:
        assert list((await session.scalars(select(RepoMatchScore))).all()) == []


async def test_late_unauthorized_response_does_not_revoke_relinked_github_token(session_factory):
    run_id, _ = await _seed(session_factory)

    async def handler(request):
        async with session_factory.begin() as session:
            await session.execute(
                update(GithubAccount).values(
                    access_token_encrypted=b"replacement", token_status="valid"
                )
            )
        return _github_reply(request, unauthorized=True)

    await _run(session_factory, run_id, handler)
    async with session_factory() as session:
        account = (await session.scalars(select(GithubAccount))).one()
    assert account.access_token_encrypted == b"replacement" and account.token_status == "valid"


async def test_unstorable_readme_is_partial_without_losing_other_repositories(session_factory):
    run_id, repo_ids = await _seed(session_factory, count=2)

    def handler(request):
        if request.url.host != "api.github.com":
            return _model_reply(repo_ids)
        if request.url.path.endswith("/repo0/readme"):
            return httpx.Response(
                200,
                json={"encoding": "base64", "content": base64.b64encode(b"bad\x00readme").decode()},
            )
        return _github_reply(request)

    await _run(session_factory, run_id, handler)
    candidates, analyses, repos = await _read(session_factory, run_id)
    assert repos[0].readme_text is None and repos[1].readme_text == "Python service README"
    snapshots = [candidate.ranking_signals["analysis"] for candidate in candidates]
    assert [snapshot["status"] for snapshot in snapshots] == ["partial", "succeeded"]
    assert snapshots[0]["error_code"] == "no_readme" and len(analyses) == 2


async def test_unstorable_language_name_is_partial_without_losing_known_languages(session_factory):
    run_id, repo_ids = await _seed(session_factory)

    def handler(request):
        if request.url.host != "api.github.com":
            return _model_reply(repo_ids)
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 100, "bad\x00language": 10})
        return _github_reply(request)

    await _run(session_factory, run_id, handler)
    candidates, _, repos = await _read(session_factory, run_id)
    assert repos[0].languages == {"Python": 100}
    assert candidates[0].ranking_signals["analysis"]["status"] == "partial"


@pytest.mark.parametrize("invalid_tech", ["Py\x00thon", "Py\ud800thon"])
async def test_unstorable_model_fields_fail_only_the_affected_repository(
    session_factory, invalid_tech
):
    run_id, repo_ids = await _seed(session_factory, count=2)

    def handler(request):
        if request.url.host == "api.github.com":
            return _github_reply(request)
        return _model_reply(repo_ids, invalid_tech=invalid_tech)

    await _run(session_factory, run_id, handler)
    candidates, analyses, _ = await _read(session_factory, run_id)
    assert [candidate.ranking_signals["analysis"]["status"] for candidate in candidates] == [
        "failed",
        "succeeded",
    ]
    failed = next(row for row in analyses if row.repository_id == repo_ids[0])
    assert failed.error_code == "llm_failed" and failed.tech_stack == [] and failed.result is None
    assert failed.raw_output is not None


async def test_unstorable_raw_model_output_is_retained_as_escaped_failure_record(session_factory):
    run_id, repo_ids = await _seed(session_factory)

    def handler(request):
        if request.url.host == "api.github.com":
            return _github_reply(request)
        payload = _model_reply(repo_ids).json()
        payload["output"][0]["content"][0]["text"] = "invalid\x00model\ud800output"
        return httpx.Response(
            200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    await _run(session_factory, run_id, handler)
    _, analyses, _ = await _read(session_factory, run_id)
    assert analyses[0].status == "failed"
    assert analyses[0].raw_output == r"invalid\u0000model\ud800output"


async def test_candidate_l1_match_card_flow_uses_only_sentence_backed_requirements(session_factory):
    from sqlalchemy import delete

    from app.core.errors import AppError
    from app.db.models.posting import JdRequirement, JobPosting
    from app.features.analysis.candidates import prepare_candidates
    from app.features.analysis.cards import get_repository_cards
    from app.features.analysis.matching import refresh_matches
    from app.shared.enums import Reason

    run_id, repo_ids = await _seed(session_factory, count=2)
    async with session_factory.begin() as session:
        await session.execute(delete(AnalysisRepoCandidate))
        await session.execute(update(Repository).values(size_kb=100))
        posting = JobPosting(
            normalized_url="https://www.wanted.co.kr/wd/1",
            raw_url="https://www.wanted.co.kr/wd/1",
            parse_status="succeeded",
            skill_tags=["Python"],
        )
        session.add(posting)
        await session.flush()
        await session.execute(
            update(AnalysisJob).where(AnalysisJob.id == run_id).values(job_posting_id=posting.id)
        )
        requirements = [
            JdRequirement(
                job_posting_id=posting.id,
                category="required",
                text=sentence,
                display_order=n,
                tech_tags=["Python"],
            )
            for n, sentence in enumerate(["Python 개발 경험", "협업 경험"])
        ]
        session.add_all(requirements)
        await session.flush()
        expected_requirement_id = requirements[0].id
        await prepare_candidates(
            session, run_id, portfolio_full_names=["OWNER/REPO0"], min_size_kb=50
        )
    await _run(
        session_factory,
        run_id,
        lambda request: (
            _github_reply(request)
            if request.url.host == "api.github.com"
            else _model_reply(repo_ids)
        ),
    )
    async with session_factory.begin() as session:
        with pytest.raises(AppError) as caught:
            await get_repository_cards(session, run_id)
        assert caught.value.reason == Reason.NOT_READY
    async with session_factory.begin() as session:
        await refresh_matches(session, run_id)
        cards = await get_repository_cards(session, run_id)
    assert len(cards) == 2
    assert all(card.recommended and card.match_score is None for card in cards)
    assert all(card.matched_requirement_ids == [expected_requirement_id] for card in cards)
    assert cards[0].candidate_source == "both" and cards[1].candidate_source == "rule_filter"
