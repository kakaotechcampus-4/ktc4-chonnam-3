"""README 축약 캐시가 재호출만 줄이고 추천·실패 정책은 유지하는지 검증한다."""

from dataclasses import replace
from uuid import UUID

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select, update

from app.db.models.analysis import AnalysisJob
from app.db.models.github import RepoAnalysis
from app.db.models.posting import JobPosting
from app.features.analysis.cards import get_repository_cards
from app.features.analysis.matching import refresh_matches
from tests.features.analysis.test_repo_analyze import (
    _github_reply,
    _model_reply,
    _read,
    _run,
    _seed,
)


@pytest.mark.parametrize(
    ("case", "second_limit", "expected_calls", "expected_status"),
    [
        ("same", 5, 1, "partial"),
        ("changed_input", 9, 2, "partial"),
        ("legacy", 5, 2, "partial"),
        ("collection_error", 5, 2, "partial"),
        ("complete_input", 20000, 2, "succeeded"),
    ],
)
async def test_truncated_cache_preserves_partial_eligibility_and_retries_changed_input(
    session_factory, case, second_limit, expected_calls, expected_status
):
    run_id, repo_ids = await _seed(session_factory)
    async with session_factory.begin() as session:
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
    calls = 0
    first_collection = True

    def handler(request):
        nonlocal calls
        if request.url.host == "api.github.com":
            if case == "collection_error" and first_collection:
                if request.url.path.endswith("/commits") and "author" in request.url.params:
                    return httpx.Response(500, json={"message": "temporary failure"})
            return _github_reply(request)
        calls += 1
        return _model_reply(repo_ids)

    await _run(session_factory, run_id, handler, readme_max_chars=5)
    if case == "legacy":
        async with session_factory.begin() as session:
            analysis = (await session.scalars(select(RepoAnalysis))).one()
            # 과거 분석에는 재사용 근거가 없다. 최신 Repository 상태로 이를 추측하지 않는다.
            analysis.result = {
                key: value for key, value in analysis.result.items() if not key.startswith("_")
            }
    first_collection = False
    await _run(session_factory, run_id, handler, readme_max_chars=second_limit)
    assert calls == expected_calls
    candidates, analyses, _ = await _read(session_factory, run_id)
    assert len(analyses) == 1
    assert analyses[0].status == expected_status
    assert candidates[0].ranking_signals["analysis"]["status"] == expected_status
    assert candidates[0].ranking_signals["analysis"]["error_code"] is None
    async with session_factory.begin() as session:
        await refresh_matches(session, run_id)
        card = (await get_repository_cards(session, run_id))[0]
    assert card.status == expected_status
    assert card.recommended is (expected_status == "succeeded")
    assert card.match_score is None


def _source():
    return c.ShallowRepoInput(
        repository_id=str(UUID(int=1)),
        head_sha="a" * 40,
        description="service",
        readme_text="Pytho",
        readme_truncated=True,
        languages=(c.LanguageBytes("Python", 100),),
        commit_count=10,
        user_commit_count=3,
        collection_errors=(),
    )


def _values():
    return {
        "repository_id": UUID(int=1),
        "analysis_level": "l1",
        "head_sha": "a" * 40,
        "prompt_version": "repo_shallow_v1",
        "status": "partial",
        "error_code": None,
        "result": {"purpose": "service", "limitations": ["README truncated"]},
    }


def test_truncation_proof_preserves_result_without_retaining_input():
    from app.features.analysis.partial_cache import can_reuse_truncated, record_truncation_cache

    values = _values()
    original = dict(values["result"])
    record_truncation_cache(values, _source())
    row = RepoAnalysis(**values)
    assert can_reuse_truncated(row, _source(), "repo_shallow_v1")
    assert {key: row.result[key] for key in original} == original
    assert "Pytho" not in str(row.result)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_id", str(UUID(int=2))),
        ("head_sha", "b" * 40),
        ("description", "changed service"),
        ("readme_text", "Python service"),
        ("readme_truncated", False),
        ("languages", (c.LanguageBytes("Python", 101),)),
        ("commit_count", 11),
        ("user_commit_count", 4),
        ("collection_errors", ("rate_limited",)),
    ],
)
def test_partial_cache_requires_every_analyzed_input_field(field, value):
    from app.features.analysis.partial_cache import can_reuse_truncated, record_truncation_cache

    values = _values()
    record_truncation_cache(values, _source())
    changed = replace(_source(), **{field: value})
    assert not can_reuse_truncated(RepoAnalysis(**values), changed, "repo_shallow_v1")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("analysis_level", "l2"),
        ("prompt_version", "repo_shallow_v2"),
        ("status", "failed"),
        ("status", "succeeded"),
        ("error_code", "rate_limited"),
        ("result", {"purpose": "legacy"}),
    ],
)
def test_partial_cache_does_not_trust_failure_or_missing_proof(field, value):
    from app.features.analysis.partial_cache import can_reuse_truncated, record_truncation_cache

    values = _values()
    record_truncation_cache(values, _source())
    values[field] = value
    assert not can_reuse_truncated(RepoAnalysis(**values), _source(), "repo_shallow_v1")


def test_failed_collection_is_not_marked_as_truncation_only():
    from app.features.analysis.partial_cache import can_reuse_truncated, record_truncation_cache

    values = _values()
    source = replace(_source(), collection_errors=("repo_unreachable",))
    record_truncation_cache(values, source)
    assert not can_reuse_truncated(RepoAnalysis(**values), _source(), "repo_shallow_v1")
