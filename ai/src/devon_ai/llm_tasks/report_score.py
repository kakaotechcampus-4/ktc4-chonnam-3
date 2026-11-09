"""면접 전체 문답에서 턴별 단계 판정을 만든다. prompt 로드·provider I/O는 BE 책임이다.

점수 환산·평균은 이 모듈이 아니라 devon_ai.report_scores가 한다. 판정은 각 턴의 답변만 근거로 하고
다른 턴에서 추론하지 않는다는 규칙은 구조로 격리하지 못하므로 prompt 지시와 검증기로 대신한다.
"""

from dataclasses import asdict
from typing import get_args

from devon_ai import contracts as c

type ScoreChecked = c.ContractChecked[c.ScoreJudgments]
SUPPORTED_PROMPT_VERSIONS = frozenset({"report_score_v1", "report_score_v2"})

# 점수를 낼 수 없는 key가 있어 실패했을 때의 error_code. 공통 호출 계층은 검증 실패를 일반 코드로
# 바꾸므로 판정 task가 이 코드로 다시 구분해 BE 실패 기록이 사유를 잃지 않게 한다.
UNSCORABLE_CODE = "report_score_unscorable"


def _referenced_jd(turn: c.ScoreTurn) -> frozenset[str]:
    return frozenset(item.id for item in turn.jd_requirements) | frozenset(
        ref.id for ref in turn.question_contract.basis_refs if ref.kind == "jd_requirement"
    )


def _output_schema() -> dict[str, object]:
    item = {
        "type": "object",
        "properties": {
            "turn_id": {"type": "string"},
            "key": {"enum": list(get_args(c.ScoreKeyId))},
            "level": {"enum": [0, 1, 2, 3, 4, "not_applicable"]},
        },
        "required": ["turn_id", "key", "level"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"judgments": {"type": "array", "items": item}},
        "required": ["judgments"],
        "additionalProperties": False,
    }


def check_input(turns: tuple[c.ScoreTurn, ...], rubric: tuple[c.RubricLevel, ...]) -> None:
    if type(turns) is not tuple or not turns or any(type(t) is not c.ScoreTurn for t in turns):
        raise c.ContractError("schema", "turns")
    if len({t.turn_id for t in turns}) != len(turns):
        raise c.ContractError("semantic", "turn_id")
    if type(rubric) is not tuple or any(type(r) is not c.RubricLevel for r in rubric):
        raise c.ContractError("schema", "rubric")
    # 모든 key의 0~4단계 문구가 정확히 하나씩 있어야 모델이 기준 없이 판정하지 않는다.
    expected = {(key, level) for key in get_args(c.ScoreKeyId) for level in range(5)}
    pairs = [(r.key, r.level) for r in rubric]
    if len(set(pairs)) != len(pairs) or set(pairs) != expected:
        raise c.ContractError("semantic", "rubric")


def _payload(
    turns: tuple[c.ScoreTurn, ...],
    rubric: tuple[c.RubricLevel, ...],
    supplemental_sources: tuple[c.SupplementalSource, ...] = (),
    limitations: tuple[str, ...] = (),
    evidence: tuple[c.Evidence, ...] = (),
    tool_results: tuple[c.ReportToolResult, ...] = (),
    source_notes: tuple[c.JDSourceNote, ...] = (),
) -> dict[str, object]:
    # Persona는 후보 key를 정하는 데만 쓰고 모델에는 후보 key 목록으로만 전달한다.
    return {
        "turns": [
            {
                "turn_id": turn.turn_id,
                "question": turn.question,
                "answer": turn.answer,
                "question_contract": asdict(turn.question_contract),
                "candidate_keys": list(c.score_candidate_keys(turn)),
                "jd_requirement_ids": list(turn.jd_requirement_ids),
                "jd_requirements": [asdict(item) for item in turn.jd_requirements],
            }
            for turn in turns
        ],
        "rubric": [asdict(item) for item in rubric],
        "supplemental_sources": [asdict(item) for item in supplemental_sources],
        "limitations": list(limitations),
        "evidence": [asdict(item) for item in evidence],
        "tool_results": [asdict(item) for item in tool_results],
        "source_notes": [asdict(item) for item in source_notes],
    }


async def judge_scores(
    turns: tuple[c.ScoreTurn, ...],
    *,
    rubric: tuple[c.RubricLevel, ...],
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[ScoreChecked],
    max_attempts: int = 2,
    supplemental_sources: tuple[c.SupplementalSource, ...] = (),
    limitations: tuple[str, ...] = (),
    evidence: tuple[c.Evidence, ...] = (),
    tool_results: tuple[c.ReportToolResult, ...] = (),
    source_notes: tuple[c.JDSourceNote, ...] = (),
) -> c.ModelResult[ScoreChecked]:
    """턴별 단계 판정 후보를 만들고 validate_score_judgments를 통과한 값만 반환한다.

    재시도는 하지 않으며 시도 횟수·시간은 공통 호출 계층이 제한한다. semantic 실패는 재호출하지
    않는다. 입력이 잘못되면 모델을 부르지 않는다.
    """
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "report_score":
            raise c.ContractError("schema", "report_score prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "report_score limits")
        check_input(turns, rubric)
        c.validate_jd_source_notes(
            source_notes,
            requirement_ids=frozenset(
                identifier for turn in turns for identifier in _referenced_jd(turn)
            ),
        )
        c.validate_supplemental_input(
            supplemental_sources,
            contracts=tuple(turn.question_contract for turn in turns),
            limitations=limitations,
        )
        if type(evidence) is not tuple or any(type(item) is not c.Evidence for item in evidence):
            raise c.ContractError("schema", "score evidence")
        if type(tool_results) is not tuple or any(
            type(item) is not c.ReportToolResult for item in tool_results
        ):
            raise c.ContractError("schema", "score tool results")
        registered = {item.evidence_id: item for item in evidence if item.evidence_id is not None}
        if len(registered) != len(evidence) or any(
            result.turn_id not in {turn.turn_id for turn in turns}
            or any(
                item.evidence_id is None or registered.get(item.evidence_id) != item
                for item in result.result.items
            )
            for result in tool_results
        ):
            raise c.ContractError("semantic", "score source references")
        request = c.ModelRequest(
            prompt=prompt,
            payload=_payload(
                turns,
                rubric,
                supplemental_sources,
                limitations,
                evidence,
                tool_results,
                source_notes,
            ),
            schema_name="ScoreJudgments",
            schema_version="1",
            output_schema=_output_schema(),
            limits=limits,
            max_attempts=max_attempts,
        )
    except c.ContractError as exc:
        failure = c.CallFailure(exc.stage, "report_score_input_invalid", "Score input rejected.")
        return c.ModelResult(None, failure, ())

    unscorable: list[bool] = []

    def validate(raw: object) -> ScoreChecked:
        # 계약 밖의 필드(점수 등)는 중첩 객체까지 조용히 버리지 않고 schema 실패로 처리한다.
        if type(raw) is not dict or set(raw) != {"judgments"}:
            raise c.ContractError("schema", "ScoreJudgments")
        try:
            return c.validate_score_judgments(c.decode_strict(c.ScoreJudgments, raw), turns=turns)
        except c.ContractError as exc:
            unscorable[:] = [exc.field == "unscorable key"]
            raise

    result = await model_call(request, validate)
    if result.data is None:
        if unscorable == [True] and result.failure is not None:
            failure = c.CallFailure(result.failure.stage, UNSCORABLE_CODE, "No scorable turn.")
            return c.ModelResult(None, failure, result.attempts)
        return result
    # 주입된 callable이 validator를 생략했더라도 이 문답 기준으로 다시 확인한다.
    checked = result.data
    if type(checked) is not c.ContractChecked or type(checked.data) is not c.ScoreJudgments:
        raise TypeError("ModelCall did not return checked ScoreJudgments")
    try:
        c.validate_score_judgments(checked.data, turns=turns)
    except c.ContractError as exc:
        failure = c.CallFailure(exc.stage, "report_score_invalid", "Score candidate rejected.")
        return c.ModelResult(None, failure, result.attempts)
    return result
