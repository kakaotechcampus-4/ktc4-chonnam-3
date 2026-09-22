"""Pure turn rules over BE-confirmed records; no persistence or session authority."""

from dataclasses import dataclass, field, replace

from devon_ai import contracts as c

PERSONAS: tuple[c.PersonaId, ...] = ("tech_lead", "hr_manager", "domain_lead")


def allowed_personas(presented: tuple[c.PersonaId, ...]) -> tuple[c.PersonaId, ...]:
    """Keep exactly the choices that can still meet both minima in nine questions.

    Six technical turns is a Director target, not an extra minimum or fixed order.
    An already impossible input fails closed instead of rewriting past Personas.
    """
    c._convert(tuple[c.PersonaId, ...], presented, "presented personas", wire=False)
    count = len(presented)
    if count > 9 or (presented and presented[0] != "hr_manager"):
        raise c.ContractError("semantic", "question count or first persona")
    tech = presented.count("tech_lead")
    other = count - tech
    if max(0, 5 - tech) + max(0, 3 - other) > 9 - count:
        raise c.ContractError("semantic", "impossible persona distribution")
    if count == 9:
        return ()
    if count == 0:
        return ("hr_manager",)
    return tuple(
        persona
        for persona in PERSONAS
        if max(0, 5 - tech - (persona == "tech_lead"))
        + max(0, 3 - other - (persona != "tech_lead"))
        <= 8 - count
    )


@dataclass(frozen=True)
class PresentedQuestion:
    """BE-issued identity and exact confirmed question, not a publication command."""

    question_id: str
    question: c.ContractChecked[c.Question] = field(repr=False)

    def __post_init__(self) -> None:
        c._convert(str, self.question_id, "question identity", wire=False)
        c._checked_data(self.question, c.Question)


@dataclass(frozen=True)
class TurnProgress:
    """Read-only projection of BE records; tuple position is the original Turn.

    history includes only answers whose processing BE has completed. Submitted
    but unprocessed answers, model attempts and Tool retries do not advance it.
    This is not a DB schema or a concurrent session state machine.
    """

    questions: tuple[PresentedQuestion, ...] = field(default=(), repr=False)
    history: tuple[c.AnalysisHistory, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if type(self.questions) is not tuple or any(
            type(item) is not PresentedQuestion for item in self.questions
        ):
            raise c.ContractError("schema", "presented questions")
        if type(self.history) is not tuple or any(
            type(item) is not c.AnalysisHistory for item in self.history
        ):
            raise c.ContractError("schema", "completed history")
        c._unique(tuple(item.question_id for item in self.questions), "question identities")
        allowed_personas(tuple(item.question.data.persona for item in self.questions))
        if self.question_count - self.completed_count not in (0, 1):
            raise c.ContractError("semantic", "unprocessed question count")
        for turn, record in enumerate(self.history, 1):
            if record.answer.turn != turn or record.question != self.questions[turn - 1].question:
                raise c.ContractError("semantic", "completed answer binding")

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def completed_count(self) -> int:
        return len(self.history)


def finish_allowed(progress: TurnProgress) -> bool:
    """Normal completion eligibility only; BE must still check current session state."""
    if type(progress) is not TurnProgress:
        raise c.ContractError("schema", "turn progress")
    return progress.completed_count == 9


def record_question(progress: TurnProgress, ready: c.QuestionReady) -> TurnProgress:
    """Project one confirmed question; retries/candidates alone never call this."""
    if type(progress) is not TurnProgress or type(ready) is not c.QuestionReady:
        raise c.ContractError("schema", "confirmed question input")
    if type(ready.result) is not c.ModelSuccess:
        raise c.ContractError("schema", "successful question required")
    value = c._checked_data(ready.result.data, c.Question)
    c._convert(int, ready.turn, "question turn", wire=False)
    if (
        progress.question_count != progress.completed_count
        or ready.turn != progress.question_count + 1
    ):
        raise c.ContractError("semantic", "question turn order")
    if value.persona not in allowed_personas(
        tuple(item.question.data.persona for item in progress.questions)
    ):
        raise c.ContractError("semantic", "persona quota")
    return replace(
        progress,
        questions=(*progress.questions, PresentedQuestion(ready.question_id, ready.result.data)),
    )


def complete_answer(progress: TurnProgress, record: c.AnalysisHistory) -> TurnProgress:
    """Project completed analysis once; preserve the original question and all prior records."""
    if type(progress) is not TurnProgress or type(record) is not c.AnalysisHistory:
        raise c.ContractError("schema", "processed answer input")
    if progress.question_count != progress.completed_count + 1:
        raise c.ContractError("semantic", "no pending answer")
    return replace(progress, history=(*progress.history, record))


def plan_question(
    progress: TurnProgress,
    question_id: str,
    contract: c.QuestionContract,
    *,
    remaining_candidates: int,
) -> c.QuestionPlan:
    """Attach computed turn permissions to a caller-prepared purpose, without advancing."""
    if type(progress) is not TurnProgress:
        raise c.ContractError("schema", "turn progress")
    if progress.question_count != progress.completed_count or finish_allowed(progress):
        raise c.ContractError("semantic", "next question unavailable")
    if question_id in {item.question_id for item in progress.questions}:
        raise c.ContractError("semantic", "reused question identity")
    return c.QuestionPlan(
        question_id,
        progress.question_count + 1,
        contract,
        allowed_personas(tuple(item.question.data.persona for item in progress.questions)),
        remaining_candidates,
    )


def validate_turn_decision(
    progress: TurnProgress,
    candidate: c.DirectorDecision,
    *,
    question: c.ContractChecked[c.Question] | None = None,
    allowed_locations: frozenset[tuple[str, str, str]] = frozenset(),
) -> c.ContractChecked[c.DirectorDecision]:
    """Use computed finish/ask permissions, never a model-provided completion flag."""
    if type(progress) is not TurnProgress:
        raise c.ContractError("schema", "turn progress")
    c._convert(c.DirectorDecision, candidate, "decision", wire=False)
    if progress.question_count != progress.completed_count:
        raise c.ContractError("semantic", "answer processing incomplete")
    done = finish_allowed(progress)
    if done and candidate.next_step != "finish":
        raise c.ContractError("semantic", "normal interview already complete")
    return c.validate_decision(
        candidate,
        question=question,
        allowed_personas=allowed_personas(
            tuple(item.question.data.persona for item in progress.questions)
        ),
        finish_allowed=done,
        allowed_locations=allowed_locations,
    )
