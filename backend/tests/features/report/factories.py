"""리포트 테스트 데이터. 면접·턴은 ..interview.factories 를 쓴다.

task-16
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InterviewReport,
    InterviewSession,
    ReportDisagreement,
    ReportScore,
    ScoreCriterion,
)
from app.db.models.report import SCORE_KEYS

LABELS = {
    "project_understanding": "프로젝트 이해도",
    "technical_reasoning": "기술적 사고력",
    "problem_solving": "문제 해결력",
    "communication": "커뮤니케이션",
    "contribution_clarity": "기여도 명확성",
    "company_job_fit": "기업·직무 적합성",
}
FEEDBACK = [
    {"persona": p, "tags": ["태그"], "strengths": ["강점"], "improvements": ["보완"]}
    for p in ("tech_lead", "hr_manager", "domain_lead")
]
COVERAGE = {"totalRequirements": 8, "coveredRequirements": 5, "uncoveredRequirements": ["Kafka"]}


async def seed_criteria(db: AsyncSession) -> None:
    """score_criteria 6행. display_order 는 SCORE_KEYS 순서다."""
    db.add_all(
        ScoreCriterion(score_key=key, label_ko=LABELS[key], display_order=i)
        for i, key in enumerate(SCORE_KEYS)
    )
    await db.flush()


async def make_report(
    db: AsyncSession,
    interview: InterviewSession,
    *,
    scores: tuple[float, ...] = (80, 70, 60, 90, 50, 100),
    **overrides: Any,
) -> InterviewReport:
    """리포트 1개와 점수 행. scores 는 SCORE_KEYS 순서다."""
    fields: dict[str, Any] = {
        "interview_session_id": interview.id,
        "headline": "헤드라인",
        "summary": "요약",
        "total_score": sum(scores) / len(scores),
        "feedback_json": FEEDBACK,
        "coverage_json": COVERAGE,
        "generated_at": datetime.now(UTC),
    }
    report = InterviewReport(**(fields | overrides))
    db.add(report)
    await db.flush()
    db.add_all(
        ReportScore(report_id=report.id, score_key=key, score=score)
        for key, score in zip(SCORE_KEYS, scores, strict=True)
    )
    await db.flush()
    return report


async def make_disagreement(db: AsyncSession, report: InterviewReport, persona: str) -> None:
    db.add(ReportDisagreement(report_id=report.id, persona=persona, reason_type="other"))
    await db.flush()
