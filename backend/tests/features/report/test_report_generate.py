"""생성 service: 저장·검증·멱등. 모델은 fake generator 로 대체한다(LLM 미호출). task-16"""

import copy

import pytest
from sqlalchemy import func, select, update

from app.db.models import (
    InterviewReport,
    InterviewTurn,
    JdRequirement,
    PromptVersion,
    ReportScore,
)
from app.db.models.report import SCORE_KEYS
from app.features.report import service
from app.llm_tasks.report import ReportDraftInvalidError

from ..interview.factories import make_turn
from .fakes import LLM, OUTPUT, FakeGenerator


@pytest.fixture
async def prompt(db):
    db.add(
        PromptVersion(
            task_name="report",
            version="fixture-v1",
            model="fixture-model",
            template="t",
            is_active=True,
        )
    )
    await db.commit()


async def _generate(app, ctx, generator):
    interview, _ = ctx
    return await service.generate_report(
        app.state.session_factory,
        interview_id=interview.id,
        llm=LLM,
        http_client=None,
        generator=generator,
    )


async def _counts(db):
    reports = await db.scalar(select(func.count()).select_from(InterviewReport))
    scores = await db.scalar(select(func.count()).select_from(ReportScore))
    return reports, scores


async def test_saves_report_and_six_scores(app, db, ctx, prompt):
    assert await _generate(app, ctx, FakeGenerator()) == "created"
    report = await db.scalar(select(InterviewReport))
    assert (report.headline, float(report.total_score)) == ("한 줄 총평", 75.0)
    assert (report.model, report.prompt_version) == ("fixture-model", "fixture-v1")
    assert report.generated_at is not None
    assert report.feedback_json[0]["persona"] == "tech_lead"
    rows = (await db.scalars(select(ReportScore))).all()
    assert {r.score_key for r in rows} == set(SCORE_KEYS)
    assert len(rows[0].evidence_turn_ids) == 1


async def test_payload_has_only_fixed_score_keys_and_turns(app, ctx, prompt):
    generator = FakeGenerator()
    await _generate(app, ctx, generator)
    payload = generator.calls[0]
    assert payload["score_keys"] == list(SCORE_KEYS)
    assert [t["turn_no"] for t in payload["turns"]] == [1]
    assert "score_criteria" not in payload


async def test_coverage_counts_requirements_asked(app, db, ctx, prompt):
    interview, _ = ctx
    reqs = [
        JdRequirement(
            job_posting_id=interview.job_posting_id, category="required", text=name, display_order=i
        )
        for i, name in enumerate(["Kafka", "Redis"])
    ]
    db.add_all(reqs)
    await db.flush()
    turn = await make_turn(db, interview, 2, answered=True, jd_requirement_ids=[reqs[1].id])
    assert turn.status == "answered"
    await db.commit()
    await _generate(app, ctx, FakeGenerator())
    report = await db.scalar(select(InterviewReport))
    assert report.coverage_json == {
        "totalRequirements": 2,
        "coveredRequirements": 1,
        "uncoveredRequirements": ["Kafka"],
    }


async def test_rerun_is_idempotent(app, db, ctx, prompt):
    generator = FakeGenerator()
    assert await _generate(app, ctx, generator) == "created"
    assert await _generate(app, ctx, generator) == "exists"
    assert len(generator.calls) == 1
    assert await _counts(db) == (1, 6)


async def test_concurrent_insert_does_not_duplicate(app, db, ctx, prompt):
    # 입력 수집 뒤 다른 worker 가 먼저 저장한 경우: UNIQUE 충돌은 건너뛴다.
    first = FakeGenerator()

    async def racing(payload, **kwargs):
        await _generate(app, ctx, FakeGenerator())
        return await first(payload, **kwargs)

    assert await _generate(app, ctx, racing) == "exists"
    assert await _counts(db) == (1, 6)


@pytest.mark.parametrize("status", ["in_progress", "abandoned"])
async def test_skips_when_not_completed(app, db, ctx, prompt, status):
    interview, _ = ctx
    interview.status = status
    await db.commit()
    generator = FakeGenerator()
    assert await _generate(app, ctx, generator) == "skipped"
    assert generator.calls == []


async def test_skips_without_answered_turn(app, db, ctx, prompt):
    interview, _ = ctx
    await db.execute(
        update(InterviewTurn)
        .where(InterviewTurn.interview_session_id == interview.id)
        .values(status="asked")
    )
    await db.commit()
    assert await _generate(app, ctx, FakeGenerator()) == "skipped"


def _bad(mutate):
    data = copy.deepcopy(OUTPUT)
    mutate(data)
    return data


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["scores"].pop("communication"),
        lambda d: d["scores"]["communication"].update(score=101),
        lambda d: d["scores"]["communication"].update(score=None),
        lambda d: d["scores"]["communication"].update(evidence_turn_nos=[99]),
    ],
    ids=["missing_key", "out_of_range", "null_score", "unknown_turn"],
)
async def test_invalid_output_saves_nothing(app, db, ctx, prompt, mutate):
    with pytest.raises(ReportDraftInvalidError):
        await _generate(app, ctx, FakeGenerator(output=_bad(mutate)))
    assert await _counts(db) == (0, 0)
