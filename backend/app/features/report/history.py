"""완료 면접의 불변 원문으로 저장 분석·Tool 결과를 리포트 입력에 복원한다."""

import json
from dataclasses import asdict
from typing import Any, cast

from devon_ai import contracts as c
from devon_ai.llm_tasks.answer_analysis import decode_analysis_output
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Evidence,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    RepoAnalysis,
    Repository,
    SessionRepository,
)
from app.features.interview.agent_context import _document_limitations
from app.features.interview.repository_candidates import STATE_KEY, snapshot_paths
from app.features.interview.supplemental_sources import load_supplemental_sources
from app.llm_tasks.report import ReportDraftInvalidError


def _evidence(row: Evidence) -> c.Evidence:
    return c.Evidence(
        str(row.id),
        None if row.repository_id is None else str(row.repository_id),
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


def _wire(row: Evidence) -> dict[str, object]:
    return {
        "id": str(row.id),
        "usage": "tool_result",
        "source_type": row.source_type,
        "repository_id": None if row.repository_id is None else str(row.repository_id),
        "git_ref": row.git_ref,
        "path": row.path,
        "metadata_key": row.metadata_key,
        "snippet": row.snippet,
        "tool_name": row.tool_name,
        "summary": row.summary,
        "start_line": row.start_line,
        "end_line": row.end_line,
    }
