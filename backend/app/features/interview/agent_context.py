"""면접 DB의 현재 상태와 고정된 자료를 AI Context 계약으로 읽는다."""

from collections.abc import Mapping
from typing import Literal, cast
from uuid import UUID

from devon_ai import contracts as c
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evidence import Evidence
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.interview import InterviewSession, InterviewTurn, SessionRepository
from app.db.models.knowledge import DomainQuestionFrame
from app.db.models.posting import JdRequirement, JobPosting
from app.db.models.user import User

PERSONAS: tuple[c.PersonaId, ...] = ("tech_lead", "hr_manager", "domain_lead")


class AgentStateError(ValueError):
    """서비스가 분류할 고정 사유만 담고 DB 원문·식별자는 노출하지 않는다."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def allowed_personas(
    counts: Mapping[str, int], *, turn_no: int, domain_available: bool = True
) -> tuple[c.PersonaId, ...]:
    """첫 HR과 기술 최소 5·HR/도메인 합산 최소 3의 9턴 완주 가능성을 보존한다."""
    if (
        type(turn_no) is not int
        or not 1 <= turn_no <= 9
        or set(counts) != set(PERSONAS)
        or any(type(value) is not int or value < 0 for value in counts.values())
        or sum(counts.values()) != turn_no - 1
        or (turn_no > 1 and counts["hr_manager"] == 0)
    ):
        raise AgentStateError("persona_counts_invalid")
    if turn_no == 1:
        return ("hr_manager",)
    result: list[c.PersonaId] = []
    for persona in PERSONAS:
        if persona == "domain_lead" and not domain_available:
            continue
        tech = counts["tech_lead"] + (persona == "tech_lead")
        other = counts["hr_manager"] + counts["domain_lead"] + (persona != "tech_lead")
        if max(0, 5 - tech) + max(0, 3 - other) <= 9 - turn_no:
            result.append(persona)
    if not result:
        raise AgentStateError("persona_counts_invalid")
    return tuple(result)


def _fresh[T: tuple[object, ...]](query: Select[T], lock: bool) -> Select[T]:
    # 같은 세션에서 재조회해도 identity map의 이전 상태로 비교하지 않는다.
    query = query.execution_options(populate_existing=True)
    return query.with_for_update() if lock else query


def _evidence(row: Evidence, refs: Mapping[UUID, str]) -> c.Evidence | None:
    if (
        row.repository_id is None
        or row.repository_id not in refs
        or refs[row.repository_id] != row.git_ref
    ):
        return None
    try:
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
    except c.ContractError:
        # 출처가 불완전한 과거 근거는 추측해 복구하지 않고 새 Context에서 제외한다.
        return None


async def load_context(
    session: AsyncSession,
    *,
    user_id: UUID,
    interview_id: UUID,
    limits: c.ContextLimits,
    lock: bool = False,
) -> c.Context:
    """소유권·활성 상태·답변 이력·고정 SHA를 검증해 DB 원본으로만 Context를 만든다.

    lock=True는 저장 직전 재검증용이며 읽은 행을 잠근다. 트랜잭션 종료는 호출자 책임이고,
    반환값에는 세션·ORM·비밀값이 없다. Redis/context_state나 현재 HEAD로 빈 자료를 채우지 않는다.
    """
    interview = await session.scalar(
        _fresh(
            select(InterviewSession)
            .join(User, User.id == InterviewSession.user_id)
            .where(
                InterviewSession.id == interview_id,
                InterviewSession.user_id == user_id,
                User.status == "active",
            ),
            lock,
        )
    )
    if interview is None:
        raise AgentStateError("interview_unavailable")
    if (
        interview.status not in ("preparing", "in_progress")
        or interview.total_turns != 9
        or not 0 <= interview.current_turn < 9
    ):
        raise AgentStateError("interview_state_invalid")
    turns = (
        await session.scalars(
            _fresh(
                select(InterviewTurn)
                .where(InterviewTurn.interview_session_id == interview_id)
                .order_by(InterviewTurn.turn_no),
                lock,
            )
        )
    ).all()
    if (
        [turn.turn_no for turn in turns] != list(range(1, interview.current_turn + 1))
        or any(turn.status != "answered" or not turn.answer_text for turn in turns)
        or (turns and turns[0].persona != "hr_manager")
    ):
        raise AgentStateError("turn_history_invalid")
    counts: dict[str, int] = dict.fromkeys(PERSONAS, 0)
    for turn in turns:
        if turn.persona not in counts:
            raise AgentStateError("persona_counts_invalid")
        counts[turn.persona] += 1

    selected = (
        await session.execute(
            _fresh(
                select(SessionRepository, Repository)
                .join(
                    Repository,
                    Repository.id == SessionRepository.repository_id,
                )
                .where(SessionRepository.interview_session_id == interview_id)
                .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id),
                lock,
            )
        )
    ).all()
    if not 1 <= len(selected) <= 5 or any(
        repo.user_id != user_id or repo.is_private or not repo.is_accessible for _, repo in selected
    ):
        raise AgentStateError("repository_unavailable")
    if any(not selection.snapshot_head_sha for selection, _ in selected):
        raise AgentStateError("repository_snapshot_missing")
    refs = {repo.id: cast(str, selection.snapshot_head_sha) for selection, repo in selected}
    analyses = (
        await session.scalars(
            _fresh(
                select(RepoAnalysis)
                .where(
                    RepoAnalysis.repository_id.in_(refs),
                    RepoAnalysis.status.in_(("succeeded", "partial")),
                    RepoAnalysis.analysis_level.in_(("l1", "l2")),
                )
                .order_by(RepoAnalysis.id),
                lock,
            )
        )
    ).all()
    requirements = (
        await session.scalars(
            _fresh(
                select(JdRequirement)
                .where(JdRequirement.job_posting_id == interview.job_posting_id)
                .order_by(JdRequirement.display_order, JdRequirement.id),
                lock,
            )
        )
    ).all()
    evidence_rows = (
        await session.scalars(
            _fresh(
                select(Evidence)
                .where(Evidence.interview_session_id == interview_id)
                .order_by(Evidence.id),
                lock,
            )
        )
    ).all()
    frames = (
        await session.scalars(
            _fresh(
                select(DomainQuestionFrame)
                .join(
                    JobPosting,
                    JobPosting.domain_category == DomainQuestionFrame.domain_category,
                )
                .where(
                    JobPosting.id == interview.job_posting_id,
                    DomainQuestionFrame.is_active.is_(True),
                )
                .order_by(
                    DomainQuestionFrame.axis,
                    DomainQuestionFrame.display_order,
                    DomainQuestionFrame.id,
                ),
                lock,
            )
        )
    ).all()
    try:
        repositories = tuple(
            c.ContextRepository(
                str(repo.id),
                refs[repo.id],
                selection.is_primary,
                tuple(
                    str(row.id)
                    for row in analyses
                    if row.repository_id == repo.id and row.head_sha == refs[repo.id]
                ),
                (),
            )
            for selection, repo in selected
        )
        history = tuple(
            c.HistoryTurn(
                str(turn.id),
                cast(c.PersonaId, turn.persona),
                turn.question_text,
                cast(str, turn.answer_text),
                str(turn.id) if turn.analysis is not None else None,
            )
            for turn in turns
        )
        contract = c.decode(c.QuestionContract, turns[-1].question_contract) if turns else None
        return c.Context(
            interview_id=str(interview.id),
            current_turn_id=str(turns[-1].id) if turns else None,
            turn_no=interview.current_turn + 1,
            total_turns=9,
            persona_counts=tuple(c.PersonaCount(persona, counts[persona]) for persona in PERSONAS),
            allowed_personas=allowed_personas(
                counts,
                turn_no=interview.current_turn + 1,
                domain_available=bool(frames),
            ),
            jd_requirements=tuple(
                c.JDRequirement(
                    str(row.id),
                    row.text,
                    cast(Literal["required", "preferred", "responsibility"], row.category),
                    "jd_requirements.text",
                    tuple(row.tech_tags),
                )
                for row in requirements
            ),
            repositories=repositories,
            history=history,
            current_question_contract=contract,
            evidence=tuple(
                item for row in evidence_rows if (item := _evidence(row, refs)) is not None
            ),
            # DB에 별도 version 열이 없으므로 읽은 updated_at 값을 버전 스냅샷으로 전달한다.
            domain_frames=tuple(
                c.DomainFrame(
                    str(row.id),
                    row.domain_category,
                    row.updated_at.isoformat(),
                    row.frame_text,
                )
                for row in frames
            ),
            limits=limits,
        )
    except c.ContractError:
        raise AgentStateError("context_contract_invalid") from None
