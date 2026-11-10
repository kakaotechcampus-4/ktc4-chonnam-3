"""BE payload 가 AI 의 실제 generate_report 입력 계약을 통과하는지 본다(모델 호출만 대역). task-16

AI 모듈에 generate_report 가 없으면(병합 전) 건너뛴다.
"""

import importlib

import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import Evidence, InterviewReport, InterviewTurn, ReportScore, TurnEvidence
from app.db.models.report import SCORE_KEYS

from ..interview.factories import make_evidence, make_turn
from .fakes import LLM

real_generate = getattr(
    importlib.import_module("devon_ai.llm_tasks.report"), "generate_report", None
)
pytestmark = pytest.mark.skipif(real_generate is None, reason="AI generate_report 미병합")

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
            {"turn_id": turn_id, "key": key, "level": 3}
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


async def _seed(db, interview, repo, *, unanswered_extra):
    first, second = (
        await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no).limit(2))
    ).all()
    # ctx 의 1번(tech_lead)·2번(domain_lead) 턴에 질문 계약을 채운다.
    first.question_contract = second.question_contract = CONTRACT
    turns = [
        first,
        second,
        await make_turn(
            db, interview, 3, answered=True, persona="hr_manager", question_contract=CONTRACT
        ),
    ]
    if unanswered_extra:  # 시간 종료로 질문만 받고 끝난 마지막 턴
        await make_turn(db, interview, 4, persona="tech_lead", question_contract=CONTRACT)
    evidence = await make_evidence(db, interview, repo)
    db.add(TurnEvidence(turn_id=turns[0].id, evidence_id=evidence.id, usage="evaluation_basis"))
    await db.commit()
    return evidence


async def _run(app, db, ctx, *, unanswered_extra=False):
    from app.features.report import service

    interview, repo = ctx
    await _seed(db, interview, repo, unanswered_extra=unanswered_extra)
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
    outcome, _, narrative = await _run(app, db, ctx)
    assert outcome == "created"
    rows = (await db.scalars(select(ReportScore))).all()
    assert {r.score_key for r in rows} == set(SCORE_KEYS)
    assert (await db.scalar(select(InterviewReport))).headline == "근거를 갖고 설명하는 지원자"
    evidence = (await db.scalars(select(Evidence))).one()
    sent = narrative.requests[0].payload["evidence"][0]
    assert sent["repository_id"] == str(evidence.repository_id)
    assert sent["git_ref"] == evidence.git_ref


async def test_unanswered_turn_is_not_sent_to_ai(app, db, ctx, prompt):
    # 시간 종료로 답하지 못한 마지막 턴은 BE 가 입력에서 뺀다(#246). AI 는 답한 턴만 판정한다.
    outcome, score, narrative = await _run(app, db, ctx, unanswered_extra=True)
    assert outcome == "created"
    assert [t["turn_id"] for t in score.requests[0].payload["turns"]] == ["1", "2", "3"]
    assert [t["turn_id"] for t in narrative.requests[0].payload["turns"]] == ["1", "2", "3"]
