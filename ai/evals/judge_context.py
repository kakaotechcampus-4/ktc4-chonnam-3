"""사례에 실제 제공한 입력만 Judge에 전달한다. 정답·검수 정보는 투영하지 않는다."""

from __future__ import annotations

import json
import math
from typing import Any

CONTEXT_VERSION = "judge-context.v1"
MAX_CONTEXT_BYTES = 65536
_FIELDS = frozenset(
    """service_task service_input context question answer answer_text turn turn_id turn_no
    total_turns current_turn_id current_question_contract allowed_personas persona_counts
    persona_left persona count hr_manager tech_lead domain_lead history latest_analysis analysis
    rejected_candidate
    analysis_ref analysis_refs answer_analysis question_contract purpose required_points
    key description evaluation_scope evaluation_keys assumptions basis_refs follows
    parent_turn_id parent_turn_no question_type topic_code contribution_scope evidence
    evidences materials reference_texts ref id kind evidence_id repository_id git_ref path
    lines start_line end_line source_kind source_type source_field metadata_key content
    text snippet summary tool_name status items searched_scope limitations error_code
    tool_results result source_notes supplemental_sources supplemental_limitations
    external_searches external_queries repositories primary jd_requirements
    jd_requirement_ids requirements category tech_tags domain_frames version limits
    remaining_calls remaining_replans policy_version evaluation_targets keys
    evaluation_status sufficiency covered_points missing_points claim_checks claim_text
    evidence_refs needs_verification verification_requests technical_assessment explanation
    answer_quotes reason scope allowed_locations allowed_paths task tool_budget_left turns
    rubrics project_understanding technical_reasoning problem_solving communication
    contribution_clarity company_job_fit 0 1 2 3 4 source_id document_id page element
    location read_scope text_hash image_hash block_id requirement_id source_location
    comparison_status supporting_refs conflicting_refs source_limitations
    """.split()
)
_RAW_CONTAINERS = frozenset(
    "evidence evidences materials reference_texts items supplemental_sources source_notes".split()
)
_LIMITATIONS = frozenset(
    {
        "unsupported_fields_omitted",
        "unsupported_source_format",
        "raw_source_not_provided",
        "input_not_provided",
        "context_byte_limit_exceeded",
        "context_structure_limit",
        "prior_analysis_is_not_raw_source",
        "prior_candidate_is_not_raw_source",
    }
)
_CONTEXT_KEYS = {
    "schema_version",
    "source_format",
    "status",
    "source_materials_provided",
    "source",
    "limitations",
}


def _size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def build_judge_context(payload: object, *, max_bytes: int = MAX_CONTEXT_BYTES) -> dict[str, Any]:
    """원문·위치를 추정하지 않고 복사한다. 예산 초과 시 원문 일부 대신 미제공을 표시한다."""
    if type(max_bytes) is not int or max_bytes < 512 or max_bytes > MAX_CONTEXT_BYTES:
        raise ValueError("invalid Judge context byte limit")
    notes: set[str] = set()
    nodes = 0

    def project(value: object, depth: int = 0) -> Any:
        nonlocal nodes
        nodes += 1
        if depth > 24 or nodes > 20000:
            notes.add("context_structure_limit")
            return None
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if type(key) is not str or key not in _FIELDS:
                    notes.add("unsupported_fields_omitted")
                    continue
                if key in {"latest_analysis", "analysis", "answer_analysis"} and item is not None:
                    notes.add("prior_analysis_is_not_raw_source")
                if key == "rejected_candidate" and item is not None:
                    notes.add("prior_candidate_is_not_raw_source")
                result[key] = project(item, depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            return [project(item, depth + 1) for item in value]
        if value is None or type(value) in {str, int, bool}:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        notes.add("unsupported_fields_omitted")
        return None

    mapping = payload if isinstance(payload, dict) else {}
    typed = "service_task" in mapping
    if typed and (
        mapping.get("service_task")
        not in {"director", "director_verification", "answer_analysis", "report"}
        or not isinstance(mapping.get("service_input"), dict)
    ):
        notes.add("unsupported_source_format")
        source: dict[str, Any] = {}
    elif typed:
        if set(mapping) - {"service_task", "service_input"}:
            notes.add("unsupported_fields_omitted")
        source = {
            "service_task": mapping["service_task"],
            "service_input": project(mapping["service_input"]),
        }
    elif isinstance(payload, dict):
        source = project(payload)
    else:
        notes.add("input_not_provided")
        source = {}

    def has_raw(value: object, in_material: bool = False) -> bool:
        if isinstance(value, dict):
            if in_material and any(
                isinstance(value.get(key), str) and value[key].strip()
                for key in ("text", "content", "snippet")
            ):
                return True
            return any(
                has_raw(item, in_material or key in _RAW_CONTAINERS) for key, item in value.items()
            )
        return isinstance(value, list) and any(has_raw(item, in_material) for item in value)

    raw = has_raw(source)
    if not raw:
        notes.add("raw_source_not_provided")
    result: dict[str, Any] = {
        "schema_version": CONTEXT_VERSION,
        "source_format": "typed_service" if typed else "legacy",
        "status": "partial" if notes and source else "available" if source else "unavailable",
        "source_materials_provided": raw,
        "source": source,
        "limitations": sorted(notes),
    }
    if _size(result) > max_bytes:
        result.update(
            status="unavailable",
            source_materials_provided=False,
            source={},
            limitations=sorted(notes | {"context_byte_limit_exceeded"}),
        )
    return result


def validate_judge_context(value: object) -> dict[str, Any]:
    """직접 ModelJudge 호출도 같은 투영 경계를 통과시키며 외부 상태 선언은 신뢰하지 않는다."""
    if (
        not isinstance(value, dict)
        or set(value) != _CONTEXT_KEYS
        or value.get("schema_version") != CONTEXT_VERSION
        or value.get("source_format") not in {"legacy", "typed_service"}
        or value.get("status") not in {"available", "partial", "unavailable"}
        or type(value.get("source_materials_provided")) is not bool
        or not isinstance(value.get("source"), dict)
        or not isinstance(value.get("limitations"), list)
        or any(type(note) is not str or note not in _LIMITATIONS for note in value["limitations"])
    ):
        raise ValueError("invalid Judge source context")
    checked = build_judge_context(value["source"])
    checked["limitations"] = sorted(set(checked["limitations"]) | set(value["limitations"]))
    if not checked["source"]:
        checked["source_format"] = value["source_format"]
    if checked["source"] and checked["limitations"]:
        checked["status"] = "partial"
    if _size(checked) > MAX_CONTEXT_BYTES:
        checked.update(
            status="unavailable",
            source_materials_provided=False,
            source={},
            limitations=sorted(set(checked["limitations"]) | {"context_byte_limit_exceeded"}),
        )
    return checked
