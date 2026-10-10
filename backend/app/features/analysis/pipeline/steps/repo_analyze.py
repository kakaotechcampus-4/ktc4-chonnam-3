"""Task 10의 batch L0-b/L1 연결. run/API/queue 상태 확정은 Task 11이 맡는다."""

from dataclasses import dataclass, replace
from uuid import UUID

import httpx
from devon_ai import contracts as c
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings
from app.features.analysis import repo_analysis_queries as queries
from app.features.analysis.candidates import repository_summary
from app.features.analysis.matching import refresh_matches
from app.features.analysis.partial_cache import record_truncation_cache
from app.features.analysis.pipeline.steps.repo_detail import RateLimitRecorder, collect_repo_details
from app.integrations.github.base import RepoDetail, RepoSummary
from app.integrations.github.client import DEFAULT_README_MAX_CHARS, GithubClient
from app.llm_tasks.prompt_loader import load_active_prompt
from app.llm_tasks.repo_shallow import analyze_repositories, to_repo_analysis_rows


def _snapshot(
    analysis_id: UUID | None,
    head_sha: str | None,
    prompt_version: str | None,
    status: str,
    error_code: str | None,
) -> dict[str, object]:
    return {
        "analysis_id": str(analysis_id) if analysis_id is not None else None,
        "head_sha": head_sha,
        "prompt_version": prompt_version,
        "status": status,
        "error_code": error_code,
    }


def _unstorable(value: object) -> bool:
    """PostgreSQL TEXT/JSONB에 넣을 수 없는 문자만 검사한다."""
    if isinstance(value, str):
        if "\x00" in value:
            return True
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return True
    if isinstance(value, dict):
        return any(_unstorable(key) or _unstorable(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_unstorable(item) for item in value)
    return False


def _escaped_record(value: str) -> str:
    return (
        value.encode("utf-8", errors="backslashreplace").decode("utf-8").replace("\x00", "\\u0000")
    )


@dataclass
class CollectedCandidateBatch:
    """L0-b 수집 상태를 L1 단계로 전달하며 토큰은 보관하지 않는다."""

    run_id: UUID
    repositories: dict[UUID, RepoSummary]
    positions: dict[UUID, int]
    details: dict[str, RepoDetail]
    inputs: list[c.ShallowRepoInput]
    snapshots: dict[UUID, dict[str, object]]
    inaccessible: set[UUID]


async def collect_candidate_batch(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
    batch_no: int,
    *,
    github_client: GithubClient,
    github_token_encrypted: bytes,
    login: str | None,
    readme_max_chars: int = DEFAULT_README_MAX_CHARS,
    on_rate_limited: RateLimitRecorder | None = None,
) -> CollectedCandidateBatch:
    """외부 호출 중 DB transaction을 잡지 않고 상세 수집까지만 완료한다.

    github_token_encrypted는 github_client 생성 때 읽은 동일 암호문이다. 복호화는 호출자가
    맡으며, 늦은 401로 새 토큰을 폐기하지 않도록 이 값으로만 조건부 갱신한다.
    """
    async with session_factory() as session, session.begin():
        user_id, rows, token_invalid = await queries.load_batch(session, run_id, batch_no)
        repositories = {repo.id: repository_summary(repo) for _, repo in rows}
        positions = {
            repo.id: candidate.batch_rank - 1
            for candidate, repo in rows
            if candidate.batch_rank is not None
        }
    if not repositories:
        return CollectedCandidateBatch(run_id, {}, {}, {}, [], {}, set())
    if token_invalid:
        details = {
            repo.full_name: RepoDetail(errors=["token_invalid"]) for repo in repositories.values()
        }
    else:
        details = await collect_repo_details(
            github_client,
            list(repositories.values()),
            login=login,
            readme_max_chars=readme_max_chars,
            on_rate_limited=on_rate_limited,
        )

    inputs: list[c.ShallowRepoInput] = []
    snapshots: dict[UUID, dict[str, object]] = {}
    inaccessible: set[UUID] = set()
    for repository_id, repo in repositories.items():
        detail = details[repo.full_name]
        if _unstorable(detail.readme_text):
            detail = replace(
                detail,
                readme_text=None,
                errors=[*detail.errors, "no_readme"],
                collected_fields=detail.collected_fields - {"readme_text", "readme_truncated"},
            )
            details[repo.full_name] = detail
        elif detail.readme_text is not None and not detail.readme_text.strip():
            # 확인된 빈 본문은 DB에 반영하되 AI에는 근거 없음으로 전달한다.
            detail = replace(detail, errors=[*detail.errors, "no_readme"])
            details[repo.full_name] = detail
        if _unstorable(detail.languages):
            languages = {
                name: size for name, size in detail.languages.items() if not _unstorable(name)
            }
            detail = replace(
                detail,
                languages=languages,
                errors=[*detail.errors, "repo_unreachable"],
                # 전부 무효인 응답을 정상적인 빈 언어 목록으로 저장하지 않는다.
                collected_fields=(
                    detail.collected_fields
                    if languages
                    else detail.collected_fields - {"languages"}
                ),
            )
            details[repo.full_name] = detail
        if detail.repository_inaccessible:
            inaccessible.add(repository_id)
        if detail.head_sha is not None and not detail.repository_inaccessible:
            try:
                inputs.append(
                    c.ShallowRepoInput(
                        repository_id=str(repository_id),
                        head_sha=detail.head_sha,
                        description=repo.description,
                        readme_text=(
                            detail.readme_text
                            if detail.readme_text and detail.readme_text.strip()
                            else None
                        ),
                        readme_truncated=detail.readme_truncated,
                        languages=tuple(
                            c.LanguageBytes(name, size) for name, size in detail.languages.items()
                        ),
                        commit_count=detail.commit_count,
                        user_commit_count=detail.user_commit_count,
                        collection_errors=tuple(dict.fromkeys(detail.errors)),
                    )
                )
                continue
            except c.ContractError:
                # 잘못된 source 값으로 LLM을 호출하거나 DB에 가짜 SHA를 만들지 않는다.
                detail = replace(
                    detail,
                    head_sha=None,
                    errors=[*detail.errors, "repo_unreachable"],
                    collected_fields=detail.collected_fields - {"head_sha"},
                )
                details[repo.full_name] = detail
        snapshots[repository_id] = _snapshot(
            None,
            detail.head_sha,
            None,
            "failed",
            detail.errors[0] if detail.errors else "repo_unreachable",
        )

    async with session_factory() as session, session.begin():
        # 여러 run이 겹쳐도 repository 행의 잠금 순서를 일치시킨다.
        for repository_id in sorted(repositories):
            await queries.save_detail(
                session, repository_id, details[repositories[repository_id].full_name]
            )
        if any("token_invalid" in detail.errors for detail in details.values()):
            await queries.revoke_token(session, user_id, github_token_encrypted)
    return CollectedCandidateBatch(
        run_id, repositories, positions, details, inputs, snapshots, inaccessible
    )


async def analyze_collected_batch(
    session_factory: async_sessionmaker[AsyncSession],
    collected: CollectedCandidateBatch,
    *,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
    refresh_recommendations: bool = False,
) -> list[dict[str, object]]:
    """이미 수집한 자료로 L1을 실행하며 GitHub를 다시 호출하지 않는다."""
    if not collected.repositories:
        return []
    run_id = collected.run_id
    repositories, positions, details = (
        collected.repositories,
        collected.positions,
        collected.details,
    )
    inputs = collected.inputs
    snapshots = dict(collected.snapshots)
    # 프롬프트 설정 실패가 이미 확인한 토큰 폐기·L0-b 수집 기록을 되돌리지 않게 한다.
    async with session_factory() as session, session.begin():
        prompt = await load_active_prompt(session, "repo_shallow") if inputs else None
        cached = await queries.load_cached(session, inputs, prompt.version) if prompt else {}
        for item in inputs:
            repository_id = UUID(item.repository_id)
            if repository_id in cached:
                assert prompt is not None
                detail = details[repositories[repository_id].full_name]
                snapshots[repository_id] = _snapshot(
                    cached[repository_id].id,
                    item.head_sha,
                    prompt.version,
                    "partial"
                    if detail.is_partial or cached[repository_id].status == "partial"
                    else "succeeded",
                    detail.errors[0] if detail.errors else None,
                )

    missing = tuple(item for item in inputs if UUID(item.repository_id) not in cached)
    results: list[dict[str, object]] = []
    if missing:
        assert prompt is not None
        result = await analyze_repositories(
            missing, prompt=prompt, settings=settings, http_client=http_client
        )
        results = to_repo_analysis_rows(result, missing, prompt)
        sources = {UUID(item.repository_id): item for item in missing}
        for values in results:
            repository_id = UUID(str(values["repository_id"]))
            values["batch_position"] = positions.get(repository_id)
            raw = values.get("raw_output")
            if isinstance(raw, str):
                # 감사 기록은 버리지 않고 저장 불가 문자만 escape 표기로 보존한다.
                values["raw_output"] = _escaped_record(raw)
            if _unstorable(values):
                # 기술명·근거의 문자를 지워 성공처럼 만들지 않는다. 다른 repo는 계속 저장한다.
                values.update(
                    status="failed",
                    error_code="llm_failed",
                    result=None,
                    tech_stack=[],
                    summary=None,
                    notable_areas=None,
                    model=_escaped_record(str(values["model"])),
                )
            detail = details[repositories[repository_id].full_name]
            if values["status"] == "succeeded" and detail.is_partial:
                values["status"] = "partial"
                values["error_code"] = detail.errors[0] if detail.errors else None
            record_truncation_cache(values, sources[repository_id])

    async with session_factory() as session, session.begin():
        for values in sorted(results, key=lambda row: str(row["repository_id"])):
            analysis_id = await queries.save_analysis(session, values)
            repository_id = UUID(str(values["repository_id"]))
            snapshots[repository_id] = _snapshot(
                analysis_id,
                str(values["head_sha"]),
                str(values["prompt_version"]),
                str(values["status"]),
                str(values["error_code"]) if values["error_code"] is not None else None,
            )
        bound = await queries.bind_snapshots(session, run_id, snapshots, collected.inaccessible)
        if refresh_recommendations:
            # 새 snapshot과 추천을 함께 확정해 이미 완료된 page가 잠시 not_ready가 되지 않게 한다.
            # autoflush=False에서도 populate_existing 조회가 새 snapshot을 지우지 않게 한다.
            await session.flush()
            await refresh_matches(session, run_id)
        return bound


async def analyze_candidate_batch(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
    batch_no: int,
    *,
    github_client: GithubClient,
    github_token_encrypted: bytes,
    login: str | None,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
    readme_max_chars: int = DEFAULT_README_MAX_CHARS,
    on_rate_limited: RateLimitRecorder | None = None,
) -> list[dict[str, object]]:
    """기존 호출자의 L0-b/L1 통합 동작을 유지한다."""
    collected = await collect_candidate_batch(
        session_factory,
        run_id,
        batch_no,
        github_client=github_client,
        github_token_encrypted=github_token_encrypted,
        login=login,
        readme_max_chars=readme_max_chars,
        on_rate_limited=on_rate_limited,
    )
    return await analyze_collected_batch(
        session_factory, collected, settings=settings, http_client=http_client
    )
