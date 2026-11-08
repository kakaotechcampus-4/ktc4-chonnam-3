"""리포트 응답 스키마. scores[].label 은 score_criteria.label_ko 에서 온다.

openapi ReportResponse / GeneratingResponse. feedback_json·coverage_json 은 worker 가
이 모양으로 저장한다.

docs/layer-rules.md 3절 / task-04
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.shared.enums import Persona, ReasonType
from app.shared.schema import CamelModel, CamelResponse


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
    main_index: int
    follow_up_depth: int


class ReportResponse(CamelResponse):
    """openapi ReportResponse. 200."""

    interview_id: uuid.UUID
    revision: int = Field(default=1, ge=1)
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


class FeedbackDisagreementRequest(CamelModel):
    persona: Persona
    reason_type: ReasonType
    comment: str | None = Field(default=None, max_length=500)
    # 기존 최초 버전 요청만 생략을 허용하며 새 FE는 항상 읽은 버전을 보낸다.
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
