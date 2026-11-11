"""저장된 Context를 바꾸지 않고 버전별 모델 표시 자료를 구성한다."""

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from devon_ai import contracts as c

# PostingContent의 원문·직무 필드와 이미지 전사의 위치·한계만 선택한다.
# 수집 실행 이력이나 공급자 응답 전체를 모델 입력의 사실로 섞지 않는다.
_POSTING_FIELDS = frozenset(
    {
        "site_adapter",
        "fetch_url",
        "content_form",
        "raw_text",
        "image_urls",
        "position",
        "company_name",
        "industry",
        "requirements",
        "preferred_points",
        "main_tasks",
        "skill_tags",
        "intro",
        "source_blocks",
        "source_limitations",
    }
)
_CONTENT_FIELDS = frozenset(
    {
        "raw_text",
        "position",
        "requirements",
        "preferred_points",
        "main_tasks",
        "intro",
        "source_blocks",
    }
)


def _posting_view(text: str) -> str | None:
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError):
        # 기존 비구조화 공고는 새로운 파서로 의미를 추측하지 않고 원문 그대로 전달한다.
        return text
    if not isinstance(raw, dict):
        return text
    visible = {key: value for key, value in raw.items() if key in _POSTING_FIELDS}
    if not any(visible.get(key) for key in _CONTENT_FIELDS):
        return None
    image = raw.get("_image_extraction")
    if isinstance(image, dict):
        visible["_image_extraction"] = {
            key: value
            for key, value in image.items()
            if key in {"status", "limitations", "rejected", "failure"}
        }
    return json.dumps(visible, ensure_ascii=False, separators=(",", ":"))


def project_model_input(
    payload: dict[str, object],
    sources: Mapping[c.BasisRef, str],
    *,
    current_turn_id: str | None,
    structured_dialogue: bool = False,
) -> tuple[dict[str, object], dict[c.BasisRef, str]]:
    """현재 발언은 한 번만 보여 주고, 모델에 감춘 공고 참조는 허용 목록에서도 뺀다."""
    projected = deepcopy(payload)
    context = cast(dict[str, object], projected["context"])
    context.pop("current_question_contract", None)
    history = cast(list[dict[str, object]], context["history"])
    context["history"] = [item for item in history if item["turn_id"] != current_turn_id]
    previous = cast(dict[str, object], projected["prior_analyses"])
    if current_turn_id is not None:
        previous.pop(current_turn_id, None)
    visible_sources = dict(sources)
    references = []
    for ref, text in sources.items():
        if ref.kind != "job_posting":
            continue
        visible = _posting_view(text)
        if visible is None:
            visible_sources.pop(ref)
            continue
        visible_sources[ref] = visible
        references.append({"kind": ref.kind, "id": ref.id, "text": visible})
    projected["reference_texts"] = references
    projected["input_version"] = "director-input.v1"
    if structured_dialogue:
        # 질문 밖에 덧붙인 설명도 반복 판단의 근거다. 과거 목적을 추측하거나
        # covered_points에 인용되지 않은 답변을 버리지 않고 같은 턴의 분석을 붙인다.
        answered_turns = []
        for turn in cast(list[dict[str, object]], context.pop("history")):
            turn_id = cast(str, turn["turn_id"])
            analysis = previous.get(turn_id)
            answered_turns.append(
                {
                    **turn,
                    "goal_source": "question",
                    "analysis": analysis,
                    "analysis_status": "provided" if analysis is not None else "unavailable",
                }
            )
        projected.pop("prior_analyses")
        projected["answered_turns"] = answered_turns
        projected["input_version"] = "director-input.v2"
    return projected, visible_sources
