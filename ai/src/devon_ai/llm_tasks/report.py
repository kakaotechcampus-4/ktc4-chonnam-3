"""종합·Persona별 서술 후보를 만든다. prompt 로드·provider I/O·저장은 BE 책임이다.

서술 출력에는 점수가 없다. 점수는 llm_tasks.report_score의 단계 판정과 devon_ai.report_scores가
만들며 이 task는 점수 판정 결과를 입력으로 받지 않는다. 보완 반영 여부, 코드 존재와 개인 기여의
분리, unresolved 불일치를 거짓말로 쓰지 않는 것 같은 의미 품질은 검증기가 아니라 평가 사례로 본다.
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import cast

from devon_ai import contracts as c
from devon_ai.llm_tasks import report_score
from devon_ai.report_scores import compute_scores

type NarrativeChecked = c.ContractChecked[c.ReportNarrative]


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _output_schema() -> dict[str, object]:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    claim = _object({"text": text, "turn_refs": texts, "evidence_refs": texts})
    claims = {"type": "array", "items": claim}
    summary = _object(
        {"strengths": claims, "gaps": claims, "follow_ups": claims, "practice_actions": claims}
    )
    persona = _object(
        {
            "persona": {"enum": list(c.NARRATIVE_PERSONAS)},
            "tags": texts,
            "strengths": claims,
            "improvements": claims,
            "practice_actions": claims,
            "limitations": texts,
        }
    )
    return _object(
        {
            "headline": text,
            "summary": summary,
            "persona_feedbacks": {"type": "array", "items": persona},
        }
    )


def _payload(report_input: c.ReportInput) -> dict[str, object]:
    return {
        "turns": [
            {
                "turn_id": turn.turn_id,
                "persona": turn.persona,
                "question": turn.question,
                "answer": turn.answer,
                "question_contract": asdict(turn.question_contract),
                "follows": turn.follows,
                "evidence_refs": list(turn.evidence_refs),
                "analysis": None if turn.analysis is None else asdict(turn.analysis),
            }
            for turn in report_input.turns
        ],
        "evidence": [asdict(item) for item in report_input.evidence],
        "tool_results": [
            {"turn_id": item.turn_id, "result": asdict(item.result)}
            for item in report_input.tool_results
        ],
    }


async def write_narrative(
    report_input: c.ReportInput,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[NarrativeChecked],
    max_attempts: int = 2,
) -> c.ModelResult[NarrativeChecked]:
    """서술 후보를 만들고 validate_narrative를 통과한 값만 반환한다.

    재시도는 하지 않으며 시도 횟수·시간은 공통 호출 계층이 제한한다. semantic 실패는 재호출하지
    않는다. 입력이 잘못되면 모델을 부르지 않는다.
    """
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "report":
            raise c.ContractError("schema", "report prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "report limits")
        c.validate_report_input(report_input)
        request = c.ModelRequest(
            prompt=prompt,
            payload=_payload(report_input),
            schema_name="ReportNarrative",
            schema_version="1",
            output_schema=_output_schema(),
            limits=limits,
            max_attempts=max_attempts,
        )
    except c.ContractError as exc:
        failure = c.CallFailure(exc.stage, "report_input_invalid", "Report input rejected.")
        return c.ModelResult(None, failure, ())

    def validate(raw: object) -> NarrativeChecked:
        # 계약 밖의 필드(점수 등)는 중첩 객체까지 조용히 버리지 않고 schema 실패로 처리한다.
        if type(raw) is not dict or set(raw) != {"headline", "summary", "persona_feedbacks"}:
            raise c.ContractError("schema", "ReportNarrative")
        return c.validate_narrative(
            c.decode_strict(c.ReportNarrative, raw), report_input=report_input
        )

    result = await model_call(request, validate)
    if result.data is None:
        return result
    # 주입된 callable이 validator를 생략했더라도 이 입력 기준으로 다시 확인한다.
    checked = result.data
    if type(checked) is not c.ContractChecked or type(checked.data) is not c.ReportNarrative:
        raise TypeError("ModelCall did not return a checked ReportNarrative")
    try:
        c.validate_narrative(checked.data, report_input=report_input)
    except c.ContractError as exc:
        failure = c.CallFailure(exc.stage, "report_invalid", "Narrative candidate rejected.")
        return c.ModelResult(None, failure, result.attempts)
    return result


# --- BE 진입점 -------------------------------------------------------------------------------
# BE(#153)의 ReportGenerator Protocol이 부르는 단일 함수다. 점수 판정과 서술 두 task를 동시에
# 호출하고 점수는 코드로 계산해 BE validate_draft가 받는 모양으로 돌려준다. 실패는 ContractError다.

_SECTIONS = (
    ("strengths", "강점"),
    ("gaps", "부족한 점"),
    ("follow_ups", "확인할 점"),
    ("practice_actions", "연습할 점"),
)


def _mapping(raw: object, name: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise c.ContractError("schema", name)
    return cast(Mapping[str, object], raw)


def _items(raw: object, name: str) -> list[object]:
    if not isinstance(raw, list | tuple):
        raise c.ContractError("schema", name)
    return list(raw)


def _level(raw: object) -> int:
    if type(raw) is not str or not raw.isdigit():
        raise c.ContractError("schema", "rubric level")
    return int(raw)


def _evidence(raw: object) -> c.Evidence:
    """BE 필드명(id·source_type·snippet)을 계약 필드로 옮긴다. 없는 필드는 보정하지 않는다."""
    item = _mapping(raw, "evidence")
    return c.decode(
        c.Evidence,
        {
            "evidence_id": item.get("id"),
            "repository_id": item.get("repository_id"),
            "git_ref": item.get("git_ref"),
            "source_kind": item.get("source_type"),
            "path": item.get("path"),
            "metadata_key": item.get("metadata_key"),
            "content": item.get("snippet"),
            "tool_name": item.get("tool_name"),
            "summary": item.get("summary"),
            "start_line": item.get("start_line"),
            "end_line": item.get("end_line"),
        },
    )


def _requirements(raw: object) -> dict[str, dict[str, object]]:
    """payload의 공고 요구사항을 id로 찾을 수 있게 모은다."""
    found: dict[str, dict[str, object]] = {}
    for item in _items(raw, "requirements"):
        entry = _mapping(item, "requirement")
        key = entry.get("id")
        if type(key) is not str or key in found:  # 같은 ID의 다른 본문을 조용히 고르지 않는다.
            raise c.ContractError("semantic", "requirements")
        found[key] = {
            "id": key,
            "category": entry.get("category"),
            "text": entry.get("text"),
        }
    return found


def _linked(raw: object, requirements: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """턴이 연결한 요구사항 ID를 본문으로 옮긴다. payload에 없는 ID는 보정하지 않고 거절한다."""
    ids = _items(raw, "jd_requirement_ids")
    if len(set(map(str, ids))) != len(ids) or any(
        type(i) is not str or i not in requirements for i in ids
    ):
        raise c.ContractError("semantic", "jd_requirement_ids")
    return [requirements[cast(str, i)] for i in ids]


def _build_inputs(
    payload: Mapping[str, object],
) -> tuple[tuple[c.ScoreTurn, ...], tuple[c.RubricLevel, ...], c.ReportInput]:
    """BE payload를 두 task의 입력 계약으로 옮긴다. turn_id는 str(turn_no)다."""
    rubric = tuple(
        c.decode(c.RubricLevel, {"key": key, "level": _level(level), "text": text})
        for key, levels in _mapping(payload.get("rubrics"), "rubrics").items()
        for level, text in _mapping(levels, "rubric").items()
    )
    requirements = _requirements(payload.get("requirements"))
    score_turns: list[c.ScoreTurn] = []
    report_turns: list[c.ReportTurn] = []
    evidence: dict[str, c.Evidence] = {}
    for raw_turn in _items(payload.get("turns"), "turns"):
        turn = _mapping(raw_turn, "turn")
        if type(turn.get("turn_no")) is not int:
            raise c.ContractError("schema", "turn_no")
        turn_id = str(turn["turn_no"])
        refs: list[str] = []
        for raw_item in _items(turn.get("evidences", []), "evidences"):
            item = _evidence(raw_item)
            evidence.setdefault(cast(str, item.evidence_id), item)
            if item.evidence_id not in refs:  # 같은 근거가 질문 근거이자 평가 근거일 수 있다.
                refs.append(cast(str, item.evidence_id))
        # BE는 미답변 턴을 빈 문자열로 보낸다. 질문했지만 답하지 않은 턴은 None으로 구분한다.
        answer = turn.get("answer")
        if type(answer) is str and not answer.strip():
            answer = None
        score_turn = c.decode(
            c.ScoreTurn,
            {
                "turn_id": turn_id,
                "persona": turn.get("persona"),
                "question": turn.get("question"),
                "answer": answer,
                "question_contract": turn.get("question_contract"),
                "jd_requirements": _linked(turn.get("jd_requirement_ids", []), requirements),
            },
        )
        parent, analysis = turn.get("parent_turn_no"), turn.get("analysis")
        score_turns.append(score_turn)
        report_turns.append(
            c.ReportTurn(
                turn_id=turn_id,
                persona=score_turn.persona,
                question=score_turn.question,
                answer=score_turn.answer,
                follows=None if parent is None else str(parent),
                analysis=None if analysis is None else c.decode(c.AnswerAnalysis, analysis),
                evidence_refs=tuple(refs),
                question_contract=score_turn.question_contract,
            )
        )
    # 근거 조회 결과(ToolResult)는 BE가 저장하지 않아 비워 둔다.
    report_input = c.ReportInput(tuple(report_turns), tuple(evidence.values()), ())
    return tuple(score_turns), rubric, report_input


def _claims(items: tuple[c.NarrativeClaim, ...]) -> list[str]:
    return [item.text for item in items]


_PERSONA_LABELS = {
    "hr_manager": "인사 담당",
    "tech_lead": "기술 리드",
    "domain_lead": "도메인 리드",
}
_PERSONA_SECTIONS = (
    ("strengths", "강점"),
    ("improvements", "부족한 점"),
    ("practice_actions", "연습할 점"),
)


def _bullets(items: tuple[c.NarrativeClaim, ...] | list[str]) -> str:
    return "\n".join(f"- {item if isinstance(item, str) else item.text}" for item in items)


def _summary(narrative: c.ReportNarrative) -> str:
    """검증된 서술을 버리지 않고 BE summary 문자열로 합친다.

    전체 요약(summary) 배열이 모두 비어 있어도 Persona 서술이 있으면 Persona 이름과 함께 그 내용을
    쓴다. 서술과 관찰 한계가 모두 비면 검증기가 이미 거절하므로 임의 문구를 만들지 않는다.
    """
    parts = [
        f"{label}\n{_bullets(getattr(narrative.summary, name))}"
        for name, label in _SECTIONS
        if getattr(narrative.summary, name)
    ]
    if not parts:
        parts = [
            f"[{_PERSONA_LABELS[item.persona]}] {label}\n{_bullets(getattr(item, name))}"
            for item in narrative.persona_feedbacks
            for name, label in _PERSONA_SECTIONS
            if getattr(item, name)
        ]
    limits = [text for item in narrative.persona_feedbacks for text in item.limitations]
    if limits:
        parts.append(f"관찰 한계\n{_bullets(limits)}")
    return "\n\n".join(parts)


def _unwrap[T](result: c.ModelResult[c.ContractChecked[T]]) -> c.ContractChecked[T]:
    if result.data is None or result.failure is not None:
        failure = result.failure
        stage = failure.stage if failure else "semantic"
        field = failure.error_code if failure else "model_failed"
        # 공통 호출 계층은 검증 실패의 세부 field를 일반 코드로 바꾼다. 점수를 낼 수 없는 key는
        # BE가 구분해 기록하므로 field를 되살린다.
        if field == report_score.UNSCORABLE_CODE:
            raise c.ContractError("semantic", "unscorable key")
        raise c.ContractError(stage if stage in ("parse", "schema") else "semantic", field)
    return result.data


async def generate_report(
    payload: Mapping[str, object],
    *,
    prompts: Mapping[str, c.PromptSpec],
    limits: c.CallLimits,
    model_call_factory: Callable[[], c.ModelCall[object]],
) -> dict[str, object]:
    """리포트 초안을 만든다. 점수는 모델이 아니라 report_scores가 계산한다(total_score는 없다).

    model_call_factory()는 task마다 한 번씩 부른다(task별 CallBudget). 입력이 틀리면 모델을
    부르지 않고, 어느 단계든 실패하면 ContractError로 끝낸다. 보정·기본값으로 채우지 않는다.
    """
    import asyncio  # 패키지 import 시점에 불러오지 않는다(import 격리 시험)

    score_turns, rubric, report_input = _build_inputs(payload)
    score_prompt, report_prompt = prompts.get("report_score"), prompts.get("report")
    # 모델을 부르기 전에 두 task의 입력을 모두 확인한다(한쪽만 호출되고 끝나지 않게).
    if type(score_prompt) is not c.PromptSpec or score_prompt.task_name != "report_score":
        raise c.ContractError("schema", "prompts")
    if type(report_prompt) is not c.PromptSpec or report_prompt.task_name != "report":
        raise c.ContractError("schema", "prompts")
    if type(limits) is not c.CallLimits:
        raise c.ContractError("schema", "limits")
    report_score.check_input(score_turns, rubric)
    c.validate_report_input(report_input)
    # 두 task는 서로의 결과를 입력으로 받지 않아 동시에 호출한다.
    # 실제 지연·비용은 호출 metadata와 서비스 측정으로 확인한다.
    # 실패는 예외가 아니라 ModelResult로 오므로 둘 다 끝난 뒤 점수 판정부터 확인한다.
    judged_result, narrative_result = await asyncio.gather(
        report_score.judge_scores(
            score_turns,
            rubric=rubric,
            prompt=score_prompt,
            limits=limits,
            model_call=cast(c.ModelCall[report_score.ScoreChecked], model_call_factory()),
        ),
        write_narrative(
            report_input,
            prompt=report_prompt,
            limits=limits,
            model_call=cast(c.ModelCall[NarrativeChecked], model_call_factory()),
        ),
    )
    judged = _unwrap(judged_result)
    scores = compute_scores(judged)
    narrative = _unwrap(narrative_result).data
    return {
        "headline": narrative.headline,
        "summary": _summary(narrative),
        "scores": {
            key: {
                "score": score,
                "reason": None,
                "evidence_turn_nos": sorted(
                    int(j.turn_id)
                    for j in judged.data.judgments
                    if j.key == key and j.level != "not_applicable"
                ),
            }
            for key, score in scores.key_scores
        },
        "feedbacks": [
            {
                "persona": item.persona,
                "tags": list(item.tags),
                "strengths": _claims(item.strengths),
                "improvements": _claims(item.improvements),
            }
            for name in c.NARRATIVE_PERSONAS
            for item in narrative.persona_feedbacks
            if item.persona == name
        ],
    }
