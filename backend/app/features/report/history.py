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


async def enrich_report_history(
    db: AsyncSession,
    interview: InterviewSession,
    turns: list[InterviewTurn],
    payload: dict[str, object],
) -> dict[str, object]:
    """최초 JSONB는 바꾸지 않고 검증된 최종 분석과 실제 조회 상태를 전달한다."""
    state = interview.context_state or {}
    trace = state.get("evidence_tool_results", {})
    try:
        referenced = frozenset(
            ref
            for turn in turns
            if turn.question_contract is not None
            for ref in c.decode_strict(c.QuestionContract, turn.question_contract).basis_refs
            if ref.kind
            in {"document_claim", "document_visual", "external_source", "document_claim_comparison"}
        )
    except c.ContractError:
        raise ReportDraftInvalidError("history.question_contract_invalid") from None
    if not any(turn.analysis is not None for turn in turns) and not trace and not referenced:
        return payload
    try:
        if type(trace) is not dict or any(type(key) is not str for key in trace):
            raise ValueError("tool trace")
        by_id = {str(turn.id): turn for turn in turns}
        if set(trace) - set(by_id):
            raise ValueError("tool trace turn")
        selection_rows = (
            await db.execute(
                select(SessionRepository.repository_id, SessionRepository.snapshot_head_sha)
                .join(Repository, Repository.id == SessionRepository.repository_id)
                .where(
                    SessionRepository.interview_session_id == interview.id,
                    Repository.user_id == interview.user_id,
                )
            )
        ).all()
        selections = {repo_id: ref for repo_id, ref in selection_rows}
        rows = list(
            await db.scalars(select(Evidence).where(Evidence.interview_session_id == interview.id))
        )
        sources: dict[str, c.Evidence] = {}
        source_rows: dict[str, Evidence] = {}
        source_limits = payload.get("limitations", [])
        if not isinstance(source_limits, list) or any(
            type(item) is not str for item in source_limits
        ):
            raise ValueError("source limitations")
        limitations = [*source_limits, *_document_limitations(state)]
        versions = {str(key): {ref} for key, ref in selections.items() if ref is not None}
        for row in rows:
            if row.repository_id is not None:
                if row.repository_id not in selections:
                    limitations.append(f"historical_source_outside_selection:{row.id}")
                    continue
                expected = selections[row.repository_id]
                if expected is not None and row.git_ref != expected:
                    limitations.append(f"historical_source_snapshot_mismatch:{row.id}")
                    continue
                if expected is None:
                    limitations.append(
                        f"historical_repository_snapshot_missing:{row.repository_id}"
                    )
                    versions.setdefault(str(row.repository_id), set()).add(row.git_ref)
            try:
                source = _evidence(row)
            except c.ContractError:
                # 미사용 과거 자료는 한계로 제외한다. 실제 인용은 아래 참조 검증에서 거절한다.
                limitations.append(f"historical_source_invalid:{row.id}")
                continue
            sources[str(row.id)], source_rows[str(row.id)] = source, row
        locations = {
            (item.repository_id, item.git_ref, item.path)
            for item in sources.values()
            if item.repository_id is not None and item.git_ref is not None and item.path is not None
        }
        for analysis in await db.scalars(
            select(RepoAnalysis).where(
                RepoAnalysis.repository_id.in_(selections),
                RepoAnalysis.analysis_level == "l2",
                RepoAnalysis.status.in_(("succeeded", "partial")),
            )
        ):
            repo_id = str(analysis.repository_id)
            if analysis.head_sha not in versions.get(repo_id, set()):
                continue
            for area in analysis.notable_areas or []:
                if isinstance(area, dict) and type(path := area.get("path")) is str:
                    locations.add((repo_id, analysis.head_sha, path))
        supplemental = await load_supplemental_sources(db, interview.id, max_total_bytes=None)
        supplied = {c.BasisRef(item.kind, item.source_id) for item in supplemental}
        if not referenced <= supplied:
            raise ValueError("historical supplemental source unavailable")
        model_sources = await load_supplemental_sources(db, interview.id, source_refs=referenced)
        visible = {c.BasisRef(item.kind, item.source_id) for item in model_sources}
        limitations.extend(
            f"supplemental_source_outside_model_budget:{ref.kind}:{ref.id}"
            for ref in sorted(referenced - visible, key=lambda item: (item.kind, item.id))
        )
        requirements = cast(list[dict[str, object]], payload.get("requirements", []))
        jd_ids = frozenset(str(item["id"]) for item in requirements)
        supplied.update(c.BasisRef("jd_requirement", item) for item in jd_ids)
        supplied.update(c.BasisRef("evidence", item) for item in sources)
        # 공고 원문 참조는 해당 면접에 고정한 공고 ID만 허용한다.
        from app.db.models import JobPosting

        posting = await db.get(JobPosting, interview.job_posting_id)
        if posting is not None and posting.raw_payload:
            supplied.add(c.BasisRef("job_posting", str(posting.id)))
        records: dict[str, list[LLMCallRecord]] = {}
        for record in await db.scalars(
            select(LLMCallRecord)
            .where(
                LLMCallRecord.interview_session_id == interview.id,
                LLMCallRecord.task_name == "answer_analysis",
                LLMCallRecord.turn_id.in_([turn.id for turn in turns]),
            )
            .order_by(LLMCallRecord.created_at, LLMCallRecord.id)
        ):
            records.setdefault(str(record.turn_id), []).append(record)
        wire_turns = {
            item["turn_no"]: item for item in cast(list[dict[str, object]], payload["turns"])
        }
        for wire_turn in wire_turns.values():
            wire_turn["evidences"] = [
                source
                for source in cast(list[dict[str, object]], wire_turn["evidences"])
                if source["id"] in sources
            ]
        tool_results: list[dict[str, object]] = []
        for turn in turns:
            turn_records = records.get(str(turn.id), [])
            if turn.analysis is not None or turn_records:
                contract = c.decode_strict(c.QuestionContract, turn.question_contract)
                parent = next((item for item in turns if item.turn_no == turn.parent_turn_no), None)
                if turn.parent_turn_no is not None and (
                    parent is None
                    or parent.turn_no >= turn.turn_no
                    or parent.persona != turn.persona
                ):
                    raise ValueError("question parent")
                candidate = c.Question(
                    cast(c.PersonaId, turn.persona),
                    turn.question_text,
                    turn.topic_code or "historical",
                    contract,
                    tuple(ref.id for ref in contract.basis_refs if ref.kind == "evidence"),
                    tuple(str(item) for item in turn.jd_requirement_ids),
                    "main" if parent is None else "follow_up",
                    None if parent is None else str(parent.id),
                )
                prior_refs = {
                    c.BasisRef("answer_turn", str(item.id))
                    for item in turns
                    if item.turn_no < turn.turn_no and item.answer_text
                }
                question = c.validate_question(
                    candidate,
                    review=c.QuestionReview(candidate.text, contract),
                    allowed_personas=(candidate.persona,),
                    evidence_refs=frozenset(sources),
                    basis_refs=frozenset(supplied | prior_refs),
                    jd_requirement_ids=jd_ids,
                )
                if not turn.answer_text:
                    raise ValueError("analysis without answer")

                def validate(
                    raw: object,
                    prompt_version: str | None = None,
                    schema_version: str | None = None,
                    *,
                    question: c.ContractChecked[c.Question] = question,
                    answer: str = turn.answer_text,
                ) -> c.AnswerAnalysis:
                    analysis = decode_analysis_output(
                        raw,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        answer_text=answer,
                        contract=question.data.question_contract,
                    )
                    return c.validate_analysis(
                        analysis,
                        question=question,
                        answer_text=answer,
                        evidence_refs=frozenset(sources),
                        allowed_locations=frozenset(locations),
                    ).data

                selected = validate(turn.analysis) if turn.analysis is not None else None
                for record in turn_records:
                    if record.turn_no != turn.turn_no:
                        raise ValueError("analysis turn")
                    if record.failure is not None or record.discard_reason is not None:
                        limitations.append(f"answer_analysis_unapplied:{turn.turn_no}")
                        continue
                    for raw_attempt in record.attempts:
                        attempt = c.AttemptMetadata(**cast(dict[str, Any], raw_attempt))
                        if attempt.error_stage is None and attempt.raw_output is not None:
                            selected = validate(
                                json.loads(attempt.raw_output),
                                attempt.prompt_version,
                                attempt.schema_version,
                            )
                if selected is not None:
                    wire_turns[turn.turn_no]["analysis"] = json.loads(json.dumps(asdict(selected)))
                    if selected.verification_requests and str(turn.id) not in trace:
                        limitations.append(f"historical_tool_status_unavailable:{turn.turn_no}")
            if str(turn.id) in trace:
                tool = c.decode_strict(c.ToolResult, trace[str(turn.id)])
                for item in tool.items:
                    if item.evidence_id is None or sources.get(item.evidence_id) != item:
                        raise ValueError("tool source unavailable")
                    evidence_items = cast(
                        list[dict[str, object]], wire_turns[turn.turn_no]["evidences"]
                    )
                    if not any(raw["id"] == item.evidence_id for raw in evidence_items):
                        evidence_items.append(_wire(source_rows[item.evidence_id]))
                tool_results.append(
                    json.loads(json.dumps(asdict(c.ReportToolResult(str(turn.turn_no), tool))))
                )
        external_trace = state.get("external_searches", [])
        if type(external_trace) is not list:
            raise ValueError("external trace")
        for raw in external_trace:
            status = c.decode_strict(c.ExternalSearchStatus, raw)
            limitations.extend(
                f"external_search:{status.status}:{value}" for value in status.limitations
            )
            if status.status != "found":
                limitations.append(f"external_search_status:{status.status}")
        return {
            **payload,
            "tool_results": tool_results,
            "limitations": list(dict.fromkeys(limitations)),
            "supplemental_sources": [
                json.loads(json.dumps(asdict(item))) for item in model_sources
            ],
        }
    except (c.ContractError, ValueError, TypeError, KeyError):
        raise ReportDraftInvalidError("history.source_or_analysis_invalid") from None
