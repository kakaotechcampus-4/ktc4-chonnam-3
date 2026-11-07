"""BE payload 가 AI 의 실제 generate_report 입력 계약을 통과하는지 본다(모델만 대역). task-16"""

from devon_ai import contracts as c
from devon_ai.llm_tasks.report import generate_report as real_generate
from sqlalchemy import select

from app.db.models import Evidence, InterviewReport, InterviewTurn, ReportScore, TurnEvidence
from app.db.models.report import SCORE_KEYS

from ..interview.factories import make_evidence, make_turn
from .fakes import LLM

CONTRACT = {
    "purpose": "목적",
    "required_points": [{"key": "k", "description": "내용"}],
    "assumptions": [],
    "basis_refs": [],
    "evaluation_scope": "평가 범위",
}
PERSONAS = ("tech_lead", "domain_lead", "hr_manager")


def _score_output(turn_ids):
    return {
        "judgments": [
            {"turn_id": turn_id, "key": key, "level": 0 if turn_id == "3" else 3}
            for turn_id, persona in zip(turn_ids, PERSONAS, strict=True)
            for key in c.SCORE_CANDIDATE_KEYS[persona]
        ]
    }


def _claim(text="관찰"):
    return {"text": text, "turn_refs": ["1"], "evidence_refs": []}


def _narrative_output():
    return {
        "headline": "근거를 갖고 설명하는 지원자",
        "summary": {k: [_claim()] for k in ("strengths", "gaps", "follow_ups", "practice_actions")},
        "persona_feedbacks": [
            {
                "persona": name,
                "tags": ["Redis"],
                "strengths": [_claim()],
                "improvements": [_claim()],
                "practice_actions": [_claim()],
                "limitations": [],
            }
            for name in c.NARRATIVE_PERSONAS
        ],
    }


class _Provider:
    def __init__(self, raw):
        self.raw, self.requests = raw, []

    async def __call__(self, request, validate):
        self.requests.append(request)
        attempt = c.AttemptMetadata(1, "fake", "m", "v", "1", 1, None, None)
        return c.ModelResult(validate(self.raw), None, (attempt,))


async def _seed(db, interview, repo, *, answer_third):
    first = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
    first.question_contract = CONTRACT  # ctx 의 1번 턴(tech_lead)에 질문 계약을 채운다.
    turns = [
        first,
        await make_turn(
            db, interview, 2, answered=True, persona="domain_lead", question_contract=CONTRACT
        ),
        await make_turn(
            db,
            interview,
            3,
            answered=answer_third,
            persona="hr_manager",
            question_contract=CONTRACT,
        ),
    ]
    evidence = await make_evidence(db, interview, repo)
    db.add(TurnEvidence(turn_id=turns[0].id, evidence_id=evidence.id, usage="evaluation_basis"))
    await db.commit()
    return evidence


async def _run(app, db, ctx, *, answer_third):
    from app.features.report import service

    interview, repo = ctx
    await _seed(db, interview, repo, answer_third=answer_third)
    score = _Provider(_score_output(["1", "2", "3"]))
    narrative = _Provider(_narrative_output())
    providers = iter([score, narrative])

    async def generator(payload, *, prompts, limits, model_call_factory):
        return await real_generate(
            payload, prompts=prompts, limits=limits, model_call_factory=lambda: next(providers)
        )

    outcome = await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=generator,
    )
    return outcome, score, narrative


async def test_be_payload_passes_the_real_generate_report(app, db, ctx, prompt):
    outcome, _, narrative = await _run(app, db, ctx, answer_third=True)
    assert outcome == "created"
    rows = (await db.scalars(select(ReportScore))).all()
    assert {r.score_key for r in rows} == set(SCORE_KEYS)
    assert (await db.scalar(select(InterviewReport))).headline == "근거를 갖고 설명하는 지원자"
    evidence = (await db.scalars(select(Evidence))).one()
    sent = narrative.requests[0].payload["evidence"][0]
    assert sent["repository_id"] == str(evidence.repository_id)
    assert sent["git_ref"] == evidence.git_ref


async def test_unanswered_turn_reaches_ai_as_none(app, db, ctx, prompt):
    # BE 는 빈 답변을 보내고 AI 가 None(질문했지만 답하지 않음)으로 받는다.
    outcome, score, _ = await _run(app, db, ctx, answer_third=False)
    assert outcome == "created"
    assert {t["turn_id"]: t["answer"] for t in score.requests[0].payload["turns"]}["3"] is None
