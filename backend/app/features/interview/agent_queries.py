"""선택된 고정 코드 범위를 승인하고 검증된 Evidence 원문을 저장한다."""

from dataclasses import replace
from uuid import UUID, uuid4

from devon_ai import contracts as c
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.director.tools import EvidenceScope
from app.db.models import (
    Evidence,
    InterviewSession,
    RepoAnalysis,
    Repository,
    SessionRepository,
    User,
)
from app.features.interview.agent_context import AgentStateError


async def _interview(db: AsyncSession, user_id: UUID, interview_id: UUID, *, lock: bool) -> None:
    query = (
        select(InterviewSession.id)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.user_id == user_id,
            InterviewSession.status.in_(("preparing", "in_progress")),
            User.status == "active",
        )
    )
    if lock:
        query = query.with_for_update()
    if await db.scalar(query) is None:
        raise AgentStateError("interview_unavailable")


async def _scope(
    db: AsyncSession, user_id: UUID, interview_id: UUID, repository_id: UUID, *, lock: bool
) -> EvidenceScope:
    selected = (
        select(SessionRepository, Repository)
        .join(Repository, Repository.id == SessionRepository.repository_id)
        .where(
            SessionRepository.interview_session_id == interview_id,
            Repository.id == repository_id,
            Repository.user_id == user_id,
            Repository.is_private.is_(False),
            Repository.is_accessible.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        selected = selected.with_for_update()
    row = (await db.execute(selected)).one_or_none()
    if row is None:
        raise AgentStateError("repository_unavailable")
    selection, repository = row
    ref = selection.snapshot_head_sha
    if ref is None:
        raise AgentStateError("repository_snapshot_missing")
    analyses = select(RepoAnalysis.notable_areas).where(
        RepoAnalysis.repository_id == repository_id,
        RepoAnalysis.head_sha == ref,
        RepoAnalysis.analysis_level == "l2",
        RepoAnalysis.status.in_(("succeeded", "partial")),
    )
    existing = select(Evidence.path).where(
        Evidence.interview_session_id == interview_id,
        Evidence.repository_id == repository_id,
        Evidence.git_ref == ref,
        Evidence.source_type.in_(("file", "readme")),
        Evidence.path.is_not(None),
        Evidence.metadata_key.is_(None),
    )
    if lock:
        analyses = analyses.with_for_update()
        existing = existing.with_for_update()
    paths = {path for path in await db.scalars(existing) if path is not None}
    for areas in await db.scalars(analyses):
        if isinstance(areas, list):
            paths.update(
                path
                for area in areas
                if isinstance(area, dict) and isinstance(path := area.get("path"), str)
            )
    try:
        return EvidenceScope(
            str(repository.id),
            repository.github_repo_id,
            repository.full_name,
            ref,
            frozenset(paths),
        )
    except c.ContractError:
        raise AgentStateError("evidence_scope_invalid") from None


async def load_evidence_scope(
    db: AsyncSession, *, user_id: UUID, interview_id: UUID, repository_id: UUID
) -> EvidenceScope:
    """승인된 정확한 경로만 반환한다. 빈 범위에 README나 현재 HEAD를 보충하지 않는다."""
    await _interview(db, user_id, interview_id, lock=False)
    return await _scope(db, user_id, interview_id, repository_id, lock=False)


def _source(row: Evidence) -> c.Evidence:
    return c.Evidence(
        str(row.id),
        str(row.repository_id),
        row.git_ref,
        row.source_type,
        row.path,
        row.metadata_key,
        row.snippet,
        row.tool_name,
        row.summary,
        row.start_line,
        row.end_line,
    )


async def store_evidence(
    db: AsyncSession, *, user_id: UUID, interview_id: UUID, items: tuple[c.Evidence, ...]
) -> tuple[c.Evidence, ...]:
    """원문·출처를 보존하고 durable ID를 돌려준다. commit/rollback은 호출자 책임이다.

    tool_error의 검증된 일부 items도 동일하게 저장한다. 모델이 만든 metadata나
    임의 경로를 허용하지 않으며 한 항목이 거절되면 이 호출의 새 행을 추가하지 않는다.
    """
    if type(items) is not tuple or any(type(item) is not c.Evidence for item in items):
        raise AgentStateError("evidence_invalid")
    await _interview(db, user_id, interview_id, lock=True)
    scopes: dict[UUID, EvidenceScope] = {}
    pending: list[Evidence] = []
    result: list[c.Evidence] = []
    for item in items:
        if (
            item.source_kind not in ("file", "readme")
            or item.repository_id is None
            or item.path is None
            or item.metadata_key is not None
            or not item.content.strip()
            or (item.tool_name is not None and len(item.tool_name) > 50)
            or (
                item.start_line is not None
                and item.end_line is not None
                and item.end_line - item.start_line + 1
                != item.content.count("\n") + int(not item.content.endswith("\n"))
            )
        ):
            raise AgentStateError("evidence_invalid")
        try:
            repository_id = UUID(item.repository_id)
            evidence_id = UUID(item.evidence_id) if item.evidence_id is not None else None
        except ValueError:
            raise AgentStateError("evidence_invalid") from None
        if repository_id not in scopes:
            scopes[repository_id] = await _scope(
                db, user_id, interview_id, repository_id, lock=True
            )
        scope = scopes[repository_id]
        if item.git_ref != scope.git_ref or item.path not in scope.allowed_paths:
            raise AgentStateError("evidence_scope_mismatch")
        if evidence_id is not None:
            stored = await db.scalar(
                select(Evidence)
                .where(Evidence.id == evidence_id, Evidence.interview_session_id == interview_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            try:
                same_source = stored is not None and _source(stored) == item
            except c.ContractError:
                same_source = False
            if not same_source:
                raise AgentStateError("evidence_source_mismatch")
            result.append(item)
            continue
        evidence_id = uuid4()
        pending.append(
            Evidence(
                id=evidence_id,
                interview_session_id=interview_id,
                repository_id=repository_id,
                git_ref=scope.git_ref,
                source_type=item.source_kind,
                path=item.path,
                metadata_key=item.metadata_key,
                snippet=item.content,
                summary=item.summary,
                tool_name=item.tool_name,
                start_line=item.start_line,
                end_line=item.end_line,
            )
        )
        result.append(replace(item, evidence_id=str(evidence_id)))
    db.add_all(pending)
    await db.flush()
    return tuple(result)
