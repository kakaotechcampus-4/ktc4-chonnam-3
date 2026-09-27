"""검증된 AI 결과를 기존 Turn JSONB 필드 구성으로 변환한다.

권한 검사, 최초 저장값 보존과 transaction은 service가 소유한다. 이 함수는 DB 쓰기나
공개 API 직렬화를 수행하지 않으며 모델 원문과 호출 metadata를 저장값에 포함하지 않는다.
"""

from typing import Literal, cast

from devon_ai.contracts import (
    AnswerAnalysis,
    ContractChecked,
    ContractError,
    DirectorDecision,
    ModelResult,
    Question,
    to_data,
)

type TurnColumn = Literal["question_contract", "analysis", "decision"]


def to_turn_jsonb[T](
    result: ModelResult[ContractChecked[T]], *, column: TurnColumn
) -> dict[str, object]:
    """실패 결과, 미검증 후보와 대상 컬럼에 맞지 않는 타입을 거절한다."""
    if not isinstance(result, ModelResult) or not result.succeeded:
        raise ContractError("semantic", "model result")
    checked = result.data
    expected = {
        "question_contract": Question,
        "analysis": AnswerAnalysis,
        "decision": DirectorDecision,
    }
    if (
        not isinstance(checked, ContractChecked)
        or column not in expected
        or type(checked.data) is not expected[column]
    ):
        raise ContractError("semantic", "turn storage column")
    data = to_data(checked)
    if column == "question_contract":
        return cast(dict[str, object], data["question_contract"])
    return data
