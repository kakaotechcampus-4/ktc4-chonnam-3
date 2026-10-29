"""선택 run의 고정 자료를 준비하고 첫 검증된 Director 질문까지 확정한다."""

import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from pydantic import ValidationError
from sqlalchemy import JSON, and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.director.tools import EvidenceScope
from app.core.config import LLMSettings, Settings
from app.core.logging import get_logger
from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    Evidence,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    LLMCallRecord,
    RepoAnalysis,
    Repository,
    SessionRepository,
    User,
)
from app.features.analysis.analysis_results import resolve_bound_analysis
from app.features.interview import prepare_checkpoint, prepare_lease
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_context import load_answer_context
from app.features.interview.director_service import start_director
from app.features.interview.repository_sources import (
    SourceCollection,
    SourcePreparationError,
    collect_repository_sources,
)
from app.integrations.llm.client import CallBudget
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)
from app.llm_tasks.repo_deep import analyze_repository, to_repo_analysis_row

STEPS = ("analyze_repo", "build_persona", "set_criteria", "compose_question")
logger = get_logger(__name__)
type Sessions = async_sessionmaker[AsyncSession]
type Snapshot = tuple[tuple[UUID, str, bool, UUID], ...]


@dataclass(frozen=True)
class PreparedRepository:
    scope: EvidenceScope
    shallow: c.ShallowRepoAnalysis
    cached: c.DeepRepoAnalysis | None
    invalid_cache: tuple[UUID, dict[str, object] | None, list[dict[str, object]] | None] | None


def _steps(completed: int, failed: bool = False) -> list[dict[str, object]]:
    return [
        dict(
            step=step,
            status=(
                "completed"
                if index < completed
                else "failed"
                if failed and index == completed
                else "running"
                if index == completed
                else "pending"
            ),
        )
        for index, step in enumerate(STEPS)
    ]


async def _owned(db: AsyncSession, user_id: UUID, interview_id: UUID) -> InterviewSession | None:
    row: InterviewSession | None = await db.scalar(
        select(InterviewSession)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.user_id == user_id,
            User.status == "active",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return row


async def _claim(
    sessions: Sessions, user_id: UUID, interview_id: UUID, job_id: UUID
) -> bool | None:
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        if row is None or row.status != "preparing":
            return None
        first = await db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.interview_session_id == interview_id, InterviewTurn.turn_no == 1
            )
        )
        if first is not None:
            try:
                await load_answer_context(
                    db,
                    user_id=user_id,
                    interview_id=interview_id,
                    turn_no=1,
                    limits=c.ContextLimits(2, 0, "director-runtime.v1"),
                    lock=True,
                )
                valid = (
                    row.current_turn == 1
                    and first.persona == "hr_manager"
                    and first.status == "asked"
                    and first.answer_text is None
                    and bool(first.question_text.strip())
                )
            except (c.ContractError, AgentStateError):
                valid = False
            if not valid:
                row.status, row.prepare_steps = "preparing_failed", _steps(3, failed=True)
                row.last_error = dict(
                    reason="prep_failed",
                    code="prepared_question_invalid",
                    step="compose_question",
                    recoverable=True,
                    occurredAt=datetime.now(UTC).isoformat(),
                )
                prepare_lease.clear(row)
                return None
            # 질문 commit 후 상태 전이 전에 중단된 작업은 같은 질문으로 복구한다.
            row.status, row.prepare_steps, row.last_error = "in_progress", _steps(4), None
            row.started_at = row.started_at or datetime.now(UTC)
            prepare_lease.clear(row)
            return True
        state = dict(row.context_state or {})
        if state.get("prepare_job_id"):
            return None
        prepare_lease.claim(row, job_id)
        row.prepare_steps = prepare_lease.steps(row)
        row.last_error = None
        return False


async def _snapshot(
    sessions: Sessions,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
) -> tuple[c.PromptSpec, tuple[PreparedRepository, ...], Snapshot]:
    async with sessions.begin() as db:
        interview = await _owned(db, user_id, interview_id)
        if (
            interview is None
            or interview.status != "preparing"
            or not prepare_lease.owns_preparation(interview, job_id=job_id)
        ):
            raise SourcePreparationError("preparation_changed")
        # 읽은 이후 입력이 달라진 결과를 최초 checkpoint로 채택하지 않는다.
        await prepare_checkpoint.input_digest(db, interview, lock=True)
        run = await db.get(AnalysisJob, interview.analysis_job_id)
        posting = await db.get(JobPosting, interview.job_posting_id)
        if (
            run is None
            or run.user_id != user_id
            or run.job_type != "analysis_run"
            or run.status not in {"succeeded", "partial"}
            or run.job_posting_id != interview.job_posting_id
            or posting is None
            or posting.parse_status != "succeeded"
        ):
            raise SourcePreparationError("preparation_inputs_unavailable")
        prompt = await load_active_prompt(db, "repo_deep")
        await load_active_prompt(db, "director")
        await load_active_prompt(db, "answer_analysis")
        selected = (
            await db.execute(
                select(SessionRepository, Repository)
                .join(Repository, Repository.id == SessionRepository.repository_id)
                .where(SessionRepository.interview_session_id == interview_id)
                .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id)
                .with_for_update(of=SessionRepository)
            )
        ).all()
        if not 1 <= len(selected) <= 5:
            raise SourcePreparationError("repository_selection_invalid")
        candidates = (
            await db.scalars(
                select(AnalysisRepoCandidate).where(
                    AnalysisRepoCandidate.analysis_job_id == run.id,
                    AnalysisRepoCandidate.repository_id.in_([repo.id for _, repo in selected]),
                    AnalysisRepoCandidate.filter_status == "eligible",
                )
            )
        ).all()
        analyses = (
            await db.scalars(
                select(RepoAnalysis).where(
                    RepoAnalysis.repository_id.in_([repo.id for _, repo in selected])
                )
            )
        ).all()
        by_id, by_repo = (
            {row.id: row for row in analyses},
            {row.repository_id: row for row in candidates},
        )
        repositories: list[PreparedRepository] = []
        snapshot: list[tuple[UUID, str, bool, UUID]] = []
        for index, (selection, repo) in enumerate(selected):
            candidate = by_repo.get(repo.id)
            l1 = None if candidate is None else resolve_bound_analysis(candidate, by_id)
            if repo.user_id != user_id or repo.is_private or not repo.is_accessible or l1 is None:
                raise SourcePreparationError("bound_l1_unavailable")
            shallow = c.decode(c.ShallowRepoAnalysis, l1.result)
            if shallow.repository_id != str(repo.id) or shallow.head_sha != l1.head_sha:
                raise SourcePreparationError("bound_l1_invalid")
            if (
                selection.snapshot_head_sha is not None
                and selection.snapshot_head_sha != l1.head_sha
            ):
                raise SourcePreparationError("repository_snapshot_changed")
            selection.snapshot_head_sha, selection.is_primary = l1.head_sha, index < 2
            snapshot.append((repo.id, l1.head_sha, index < 2, l1.id))
            if index >= 2:
                continue
            cached: c.DeepRepoAnalysis | None = None
            invalid_cache = None
            for row in analyses:
                if (
                    row.repository_id == repo.id
                    and row.analysis_level == "l2"
                    and row.head_sha == l1.head_sha
                    and row.prompt_version == prompt.version
                    and row.status == "succeeded"
                ):
                    try:
                        checked = c.decode(c.DeepAnalysisResult, row.result)
                        value = checked.analysis
                        if (
                            value is not None
                            and value.repository_id == str(repo.id)
                            and value.head_sha == l1.head_sha
                            and 1 <= len(value.notable_areas) <= 5
                            and len({area.path for area in value.notable_areas})
                            == len(value.notable_areas)
                            and all(area.scope == "entire file" for area in value.notable_areas)
                            and tuple(
                                c.decode(c.NotableArea, area) for area in row.notable_areas or ()
                            )
                            == value.notable_areas
                        ):
                            cached = value
                    except c.ContractError:
                        pass
                    if cached is None:
                        invalid_cache = (row.id, row.result, row.notable_areas)
            repositories.append(
                PreparedRepository(
                    EvidenceScope(
                        str(repo.id), repo.github_repo_id, repo.full_name, l1.head_sha, frozenset()
                    ),
                    shallow,
                    cached,
                    invalid_cache,
                )
            )
        if await load_active_prompt(db, "repo_deep") != prompt:
            raise SourcePreparationError("preparation_inputs_changed")
        prepare_checkpoint.store(interview, await prepare_checkpoint.checked(db, interview))
        return prompt, tuple(repositories), tuple(snapshot)


async def _unchanged(
    db: AsyncSession,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    snapshot: Snapshot,
) -> InterviewSession | None:
    row = await _owned(db, user_id, interview_id)
    if (
        row is None
        or row.status != "preparing"
        or not prepare_lease.owns_preparation(row, job_id=job_id)
    ):
        return None
    selected = (
        await db.execute(
            select(SessionRepository, Repository)
            .join(Repository, Repository.id == SessionRepository.repository_id)
            .where(SessionRepository.interview_session_id == interview_id)
            .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id)
            .with_for_update()
        )
    ).all()
    if tuple(
        (repo.id, item.snapshot_head_sha, item.is_primary) for item, repo in selected
    ) != tuple(item[:3] for item in snapshot) or any(
        repo.user_id != user_id or repo.is_private or not repo.is_accessible for _, repo in selected
    ):
        return None
    candidates = (
        await db.scalars(
            select(AnalysisRepoCandidate).where(
                AnalysisRepoCandidate.analysis_job_id == row.analysis_job_id,
                AnalysisRepoCandidate.filter_status == "eligible",
            )
        )
    ).all()
    analyses = (
        await db.scalars(
            select(RepoAnalysis).where(
                RepoAnalysis.id.in_([item[3] for item in snapshot]),
            )
        )
    ).all()
    by_repo, by_id = (
        {item.repository_id: item for item in candidates},
        {item.id: item for item in analyses},
    )
    for repository_id, sha, _, analysis_id in snapshot:
        candidate = by_repo.get(repository_id)
        bound = None if candidate is None else resolve_bound_analysis(candidate, by_id)
        if bound is None or bound.id != analysis_id or bound.head_sha != sha:
            return None
    return row


async def _fail(
    sessions: Sessions,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    code: str,
    step: str,
    *,
    recoverable: bool = True,
) -> None:
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        if (
            row is None
            or row.status != "preparing"
            or (row.context_state or {}).get("prepare_job_id") != str(job_id)
        ):
            return
        _mark_failed(row, code, step, recoverable=recoverable)


def _mark_failed(row: InterviewSession, code: str, step: str, *, recoverable: bool = True) -> None:
    prepare_lease.failed(row, code, step, recoverable=recoverable)


async def _release_stale(
    db: AsyncSession,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    step: str,
) -> None:
    row = await _owned(db, user_id, interview_id)
    if (
        row is not None
        and row.status == "preparing"
        and (row.context_state or {}).get("prepare_job_id") == str(job_id)
    ):
        _mark_failed(row, "preparation_changed", step)


async def _store_analysis(
    db: AsyncSession,
    repo: PreparedRepository,
    values: dict[str, object],
) -> None:
    replaceable = RepoAnalysis.status != "succeeded"
    if repo.invalid_cache is not None:
        key, result, areas = repo.invalid_cache
        result_matches = (
            RepoAnalysis.result == result
            if result is not None
            else or_(RepoAnalysis.result.is_(None), RepoAnalysis.result == JSON.NULL)
        )
        areas_match = (
            RepoAnalysis.notable_areas == areas
            if areas is not None
            else or_(RepoAnalysis.notable_areas.is_(None), RepoAnalysis.notable_areas == JSON.NULL)
        )
        # 외부 호출 중 다른 작업이 고친 성공 캐시는 읽기 당시의 invalid 값으로 덮지 않는다.
        replaceable = or_(
            replaceable,
            and_(
                RepoAnalysis.id == key,
                result_matches,
                areas_match,
            ),
        )
    query = insert(RepoAnalysis).values(**values)
    await db.execute(
        query.on_conflict_do_update(
            constraint="uq_repo_analyses_repo_level_sha_prompt",
            set_=values,
            where=replaceable,
        )
    )


async def _may_publish(db: AsyncSession, row: InterviewSession, *, job_id: UUID) -> bool:
    if not prepare_lease.owns_preparation(row, job_id=job_id):
        return False
    try:
        await prepare_checkpoint.checked(db, row, lock=True)
    except SourcePreparationError:
        return False
    return True


async def _save_analysis(
    sessions: Sessions,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    snapshot: Snapshot,
    call_records: list[LLMCallRecord],
    pending_rows: list[tuple[PreparedRepository, dict[str, object]]],
    collected: list[tuple[PreparedRepository, c.DeepRepoAnalysis, SourceCollection]],
    failures: list[str],
    repository_limitations: dict[str, list[str]],
    step: str,
) -> bool | None:
    async with sessions.begin() as db:
        row = await _unchanged(db, user_id, interview_id, job_id, snapshot)
        if row is None:
            for record in call_records:
                record.discard_reason = "context_changed"
            db.add_all(call_records)
            await _release_stale(db, user_id, interview_id, job_id, step)
            return None
        db.add_all(call_records)
        for repo, row_values in pending_rows:
            await _store_analysis(db, repo, row_values)
        for repo, analysis, sources in collected:
            by_path = {item.path: item for item in sources.item.sources}
            for area in analysis.notable_areas:
                source = by_path.get(area.path)
                if source is None or source.kind != "file" or source.read_scope != area.scope:
                    continue
                existing = await db.scalar(
                    select(Evidence.id).where(
                        Evidence.interview_session_id == interview_id,
                        Evidence.repository_id == UUID(repo.scope.repository_id),
                        Evidence.git_ref == repo.scope.git_ref,
                        Evidence.path == source.path,
                        Evidence.snippet == source.content,
                        Evidence.tool_name.is_(None),
                    )
                )
                if existing is None:
                    db.add(
                        Evidence(
                            interview_session_id=interview_id,
                            repository_id=UUID(repo.scope.repository_id),
                            source_type="file",
                            git_ref=repo.scope.git_ref,
                            path=source.path,
                            snippet=source.content,
                            summary=area.observation,
                            tool_name=None,
                            start_line=1,
                            end_line=max(1, len(source.content.splitlines())),
                        )
                    )
            failures.extend(sources.limitations)
        if collected:
            state = dict(row.context_state or {})
            state["preparation_limitations"] = failures
            state["preparation_repository_limitations"] = repository_limitations
            row.context_state = state
            await db.flush()
            await prepare_checkpoint.complete_analysis(db, row)
            row.prepare_steps = prepare_lease.steps(row)
        else:
            state = dict(row.context_state or {})
            state["preparation_limitations"] = failures
            state["preparation_repository_limitations"] = repository_limitations
            row.context_state = state
    return bool(collected)


async def prepare_interview(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    settings: Settings,
    http_client: httpx.AsyncClient,
) -> bool:
    """외부 호출은 transaction 밖에서 하고 현재 선택·상태가 같은 결과만 적용한다."""
    job_id, step = uuid4(), "analyze_repo"
    call_records: list[LLMCallRecord] = []
    active_attempts: list[c.AttemptMetadata] = []
    active_recorded, records_saved = False, False
    heartbeat: asyncio.Task[None] | None = None
    try:
        claimed = await _claim(sessions, user_id, interview_id, job_id)
        if claimed is not False:
            return claimed is True
        prompt, repositories, snapshot = await _snapshot(sessions, user_id, interview_id, job_id)
        try:
            llm = settings.require_llm()
            prepare_lease.validate_timeout(
                settings.director_prepare_timeout_seconds, llm.llm_timeout_seconds
            )
        except (ValidationError, ValueError) as error:
            # 검증 오류의 input·본문·비밀값 대신 허용한 설정 이름만 기록한다.
            fields = (
                sorted(
                    {
                        str(item["loc"][0])
                        for item in error.errors()
                        if item["loc"] and str(item["loc"][0]) in LLMSettings.model_fields
                    }
                )
                if isinstance(error, ValidationError)
                else ["director_prepare_timeout_seconds", "llm_timeout_seconds"]
                if isinstance(error, prepare_lease.PreparationTimeoutError)
                else ["proxy_token", "chat_proxy_url"]
            )
            logger.warning("interview_prepare_config_unavailable", fields=fields)
            await _fail(
                sessions,
                user_id,
                interview_id,
                job_id,
                "llm_config_unavailable",
                step,
                recoverable=False,
            )
            return False
        heartbeat = prepare_lease.heartbeat(sessions, interview_id, job_id)
        async with sessions.begin() as db:
            row = await _unchanged(db, user_id, interview_id, job_id, snapshot)
            if row is None:
                await _release_stale(db, user_id, interview_id, job_id, step)
                return False
            prepare_checkpoint.store(row, await prepare_checkpoint.checked(db, row))
            resumed = prepare_lease.completed(row)
        collected: list[tuple[PreparedRepository, c.DeepRepoAnalysis, SourceCollection]] = []
        pending_rows: list[tuple[PreparedRepository, dict[str, object]]] = []
        failures: list[str] = []
        repository_limitations: dict[str, list[str]] = {}
        for repo in () if resumed else repositories:
            budget = CallBudget()
            active_attempts, active_recorded = [], False
            try:
                sources = await collect_repository_sources(
                    scope=repo.scope,
                    shallow=repo.shallow,
                    prompt=prompt,
                    settings=settings,
                    http_client=http_client,
                    budget=budget,
                    attempt_sink=active_attempts,
                    paths=None
                    if repo.cached is None
                    else tuple(area.path for area in repo.cached.notable_areas),
                )
                repository_limitations[repo.scope.repository_id] = list(sources.limitations)
                if repo.cached is None:
                    result = await analyze_repository(
                        sources.item,
                        snapshot_head_sha=repo.scope.git_ref,
                        prompt=prompt,
                        settings=llm,
                        http_client=http_client,
                        budget=budget,
                        attempt_sink=active_attempts,
                        source_limitations=sources.limitations,
                    )
                    call_records.append(
                        LLMCallRecord(
                            interview_session_id=interview_id,
                            task_name="repo_deep",
                            attempts=[asdict(attempt) for attempt in active_attempts],
                            failure=asdict(result.failure) if result.failure else None,
                        )
                    )
                    active_recorded = True
                    row_values = to_repo_analysis_row(result, sources.item, prompt)
                    pending_rows.append((repo, row_values))
                    if result.data is None or result.data.data.analysis is None:
                        failures.append("l2_failed")
                        continue
                    analysis = result.data.data.analysis
                else:
                    analysis = c.validate_deep_analysis(repo.cached, source=sources.item).data
                collected.append((repo, analysis, sources))
            except SourcePreparationError as error:
                failures.append(error.code)
                failures.extend(error.limitations)
                repository_limitations[repo.scope.repository_id] = [error.code, *error.limitations]
                if error.attempts:
                    call_records.append(
                        LLMCallRecord(
                            interview_session_id=interview_id,
                            task_name="repo_deep",
                            attempts=[asdict(attempt) for attempt in error.attempts],
                            failure=asdict(
                                error.failure
                                or c.CallFailure(
                                    "semantic", error.code, "L2 source preparation failed."
                                )
                            ),
                        )
                    )
                    active_recorded = True
            except c.ContractError:
                failures.append("l2_cache_source_mismatch")
                repository_limitations[repo.scope.repository_id] = ["l2_cache_source_mismatch"]
        if not resumed:
            saved = await _save_analysis(
                sessions,
                user_id,
                interview_id,
                job_id,
                snapshot,
                call_records,
                pending_rows,
                collected,
                failures,
                repository_limitations,
                step,
            )
            if saved is None:
                return False
            records_saved = True
            if not collected:
                raise SourcePreparationError(failures[0] if failures else "l2_unavailable")
        for index, phase in ((2, "build_persona"), (3, "set_criteria")):
            if resumed >= index:
                continue
            step = phase
            async with sessions.begin() as db:
                row = await _unchanged(db, user_id, interview_id, job_id, snapshot)
                if row is None:
                    await _release_stale(db, user_id, interview_id, job_id, step)
                    return False
                if phase == "build_persona":
                    await prepare_checkpoint.initialize_personas(
                        db, row, settings.persona_turn_quota
                    )
                else:
                    await prepare_checkpoint.initialize_criteria(db, row)
                row.prepare_steps = prepare_lease.steps(row)
        step = "compose_question"
        call_id = uuid4()
        async with sessions.begin() as db:
            row = await _unchanged(db, user_id, interview_id, job_id, snapshot)
            if row is None:
                await _release_stale(db, user_id, interview_id, job_id, step)
                return False
            await prepare_checkpoint.checked(db, row)
            row.context_state = {
                **(row.context_state or {}),
                "prepare_director_call_id": str(call_id),
            }
        outcome = await start_director(
            sessions,
            user_id=user_id,
            interview_id=interview_id,
            call_id=call_id,
            settings=llm,
            http_client=http_client,
            preparation_guard=partial(_may_publish, job_id=job_id),
        )
        if outcome.turn_id is None:
            async with sessions.begin() as db:
                row = await _owned(db, user_id, interview_id)
                if row is not None and prepare_lease.owns_preparation(row, job_id=job_id):
                    await prepare_checkpoint.checked(db, row)
            raise SourcePreparationError("first_question_failed")
        async with sessions.begin() as db:
            row = await _unchanged(db, user_id, interview_id, job_id, snapshot)
            if row is None:
                await _release_stale(db, user_id, interview_id, job_id, step)
                return False
            row.status, row.started_at = "in_progress", datetime.now(UTC)
            row.prepare_steps, row.last_error = _steps(4), None
            prepare_lease.clear(row)
        return True
    except (PromptNotFoundError, PromptConfigurationError):
        await _fail(sessions, user_id, interview_id, job_id, "prompt_unavailable", step)
        return False
    except (SourcePreparationError, c.ContractError) as error:
        code = (
            error.code
            if isinstance(error, SourcePreparationError)
            else "preparation_contract_invalid"
        )
        if code == "score_criteria_unavailable":
            step = "set_criteria"
        elif code == "domain_frames_unavailable":
            step = "build_persona"
        if not records_saved and call_records:
            async with sessions.begin() as db:
                for record in call_records:
                    record.discard_reason = "context_changed"
                db.add_all(call_records)
        await _fail(
            sessions,
            user_id,
            interview_id,
            job_id,
            code,
            step,
            recoverable=code not in {"preparation_inputs_changed", "preparation_outputs_changed"},
        )
        return False
    except (asyncio.CancelledError, Exception) as error:
        if active_attempts and not active_recorded:
            call_records.append(
                LLMCallRecord(
                    interview_session_id=interview_id,
                    task_name="repo_deep",
                    attempts=[asdict(attempt) for attempt in active_attempts],
                    discard_reason="canceled"
                    if isinstance(error, asyncio.CancelledError)
                    else "execution_error",
                )
            )
        if not records_saved and call_records:
            async with sessions.begin() as db:
                db.add_all(call_records)
        await _fail(sessions, user_id, interview_id, job_id, "preparation_interrupted", step)
        raise
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
