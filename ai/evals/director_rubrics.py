"""적용 가능한 기준만 편성한다. 대안 목록을 전부 필수로 해석하지 않는다."""

from collections.abc import Mapping
from typing import Any

SCENARIOS = ("partial", "sufficient", "dont_know", "contribution_correction", "tool_unavailable")
_ACTIONS = {
    "partial": "빠진 확인점 하나의 보완 또는 남은 평가 목적에 맞는 새 질문 중 하나를 선택한다.",
    "sufficient": (
        "이미 답한 내용의 단순 반복을 피하고 새로운 조건의 심화 또는 주제 전환 중 하나를 선택한다."
    ),
    "dont_know": "모름을 수용하고 접근 방법 확인 또는 다른 평가 목적의 질문 중 하나를 선택한다.",
    "contribution_correction": (
        "정정된 역할 범위를 반영한 이해 확인 또는 다른 주제 질문 중 하나를 선택한다."
    ),
    "tool_unavailable": (
        "조회 한계를 유지한 확인형·가정형 질문 또는 다른 평가 목적 질문 중 하나를 선택한다."
    ),
}


def compile_criteria(scenario: str) -> dict[str, Any]:
    """각 allowed 항목은 의무이고, next_action 안의 대안 중 하나면 충족한다."""
    if scenario not in SCENARIOS:
        raise ValueError("unknown Director scenario")
    allowed = [
        {"id": "next_action", "purpose": _ACTIONS[scenario], "logic": "one_of_allowed"},
        {"id": "one_goal", "purpose": "말로 이해할 수 있는 한 중심 목적의 명료한 질문이다."},
        {
            "id": "contract_alignment",
            "purpose": "실제 질문이 질문 계약의 목적·필수 확인내용·평가 범위와 일치한다.",
        },
        {
            "id": "context_alignment",
            "purpose": "실제 답변 원문·정정·허용 Persona·남은 평가 기회와 일치한다.",
        },
    ]
    forbidden = [
        {
            "id": "false_premise",
            "reason": "제공되지 않은 구현·경험·성과나 개인 기여를 사실로 전제한다.",
        },
        {
            "id": "false_attribution",
            "reason": "분석의 해석이나 코드 내용을 지원자가 실제 발언한 내용으로 바꾼다.",
        },
        {
            "id": "repeat_or_lead",
            "reason": "이미 충분히 답한 목적을 표현만 바꿔 반복하거나 특정 정답으로 유도한다.",
        },
        {
            "id": "unknown_as_failure",
            "reason": "정상 모름·미조회·조회 실패를 거짓 답변·기능 부재·감점의 증거로 확정한다.",
        },
    ]
    return {
        "allowed": allowed,
        "forbidden": forbidden,
        "protocol": {
            "version": "director-criteria.v1",
            "allowed_semantics": "must; alternatives within a criterion use OR",
            "forbidden_semantics": "satisfied means the forbidden behavior is absent",
            "unclear": "자료 부족은 위반이나 통과로 바꾸지 않는다.",
            "applicability": "사례에 적용하는 기준만 편성한다. 미적용과 불명을 섞지 않는다.",
            "basis": [
                {
                    "source": "technical-interview-lecture-20261105",
                    "pdf_pages": [9, 15, 29, 40, 41, 44],
                },
                {"source": "github-issue-110", "sections": [1, 3, 5]},
            ],
            "limits": "강의는 질문 설계 참고이며 수치 합격선·평가자 정확도의 검증 자료가 아니다.",
        },
    }


def derive_verdict(rubric: Mapping[str, Any], statuses: Mapping[str, str]) -> str:
    """세부 기준을 모두 판정한 뒤 종합 판정을 산출한다."""
    ids = [f"{group}:{item['id']}" for group in ("allowed", "forbidden") for item in rubric[group]]
    if len(ids) != len(set(ids)) or set(ids) != set(statuses):
        raise ValueError("criterion set mismatch")
    if any(value not in {"satisfied", "violated", "unclear"} for value in statuses.values()):
        raise ValueError("invalid criterion status")
    if "violated" in statuses.values():
        return "reject"
    return "ambiguous" if "unclear" in statuses.values() else "accept"
