"""리포트 응답 스키마. scores[].label 은 score_criteria.label_ko 에서 온다.

openapi ReportResponse / GeneratingResponse. feedback_json·coverage_json 은 worker 가
이 모양으로 저장한다.

docs/layer-rules.md 3절 / task-04
"""

import uuid
from datetime import datetime
from typing import Literal

from app.shared.enums import Persona
from app.shared.schema import CamelResponse


class ScoreItem(CamelResponse):
    """openapi ScoreItem. score 는 0~100."""

    key: str
    label: str
    score: float


class AgentFeedback(CamelResponse):
    """openapi AgentFeedback. disagreementSubmitted 는 report_disagreements 에서 온다."""

    persona: Persona
    tags: list[str]
    strengths: list[str]
    improvements: list[str]
    disagreement_submitted: bool


class ReportCoverage(CamelResponse):
    """openapi ReportCoverage. interview_reports.coverage_json 과 같은 모양이다."""

    total_requirements: int
    covered_requirements: int
    uncovered_requirements: list[str]


class ReportTurn(CamelResponse):
    """openapi InterviewTurn."""

    turn: int
    persona: Persona
    question: str
    answer: str | None


class ReportResponse(CamelResponse):
    """openapi ReportResponse. 200."""

    interview_id: uuid.UUID
    position: str
    position_label: str
    total_score: float
    headline: str
    summary: str
    scores: list[ScoreItem]
    agent_feedbacks: list[AgentFeedback]
    coverage: ReportCoverage
    turns: list[ReportTurn]
    repository_names: list[str]
    completed_at: datetime


class GeneratingResponse(CamelResponse):
    """openapi GeneratingResponse. 202 — 실패가 아니라 폴링하라는 뜻이다."""

    status: Literal["generating"] = "generating"
    retry_after: int
