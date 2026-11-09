"""6개 루브릭 시드 (label_ko 포함).

docs/db-schema.md / task-03

score_key 는 shared/enums.py ScoreKey 와 1:1 이며 CHECK 제약(SCORE_KEYS)이 이를 보장한다.
세부 기준 문구는 평가 담당 자료 보강에 따라 갱신될 수 있어 rubric 은 JSONB 로 둔다.

★ 미검수 초안이다. 신규 행은 is_active=FALSE 로 시드하며 활성화는 검수 후 별도로 한다(ADR 0018).
  기존 행은 충돌 시 rubric 만 덮어쓰고 is_active 는 유지하므로, 이미 활성인 DB 에 실행하면
  새 초안이 활성 상태로 적용된다.
  재실행 전 활성 행과 변경 문구의 검수·적용 순서를 확인해야 한다.
★ rubric 0~4단계를 공개 점수로 바꾸는 단계별 고정 점수는 LEVEL_SCORES 다. 환산은 모델이
  하지 않고 코드가 한다.
★ 0단계는 "질문을 받고도 답하지 못함"만 뜻한다. 질문하지 않았거나 근거가 부족한 항목,
  LLM 판정 실패는 점수가 아니라 미관찰·실패이므로 어느 단계에도 대응하지 않는다(task-11).
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# rubric 단계 → 공개 점수(0~100). 100점은 도달하지 않는다(만점 남발 방지).
LEVEL_SCORES: dict[str, int] = {"0": 0, "1": 20, "2": 45, "3": 70, "4": 90}


@dataclass(frozen=True, slots=True)
class ScoreCriterionSpec:
    """score_criteria 한 행. rubric 은 "0"~"4" 키를 갖는 단계별 기준이다."""

    score_key: str
    label_ko: str
    description: str
    rubric: dict[str, str]
    display_order: int


SCORE_CRITERIA: tuple[ScoreCriterionSpec, ...] = (
    ScoreCriterionSpec(
        score_key="project_understanding",
        label_ko="프로젝트 이해도",
        description="선택한 저장소의 구조·목적·핵심 기능을 얼마나 정확히 설명하는가.",
        rubric={
            "0": "질문을 받았지만 프로젝트의 목적이나 핵심 기능을 설명하지 못한다.",
            "1": "목적이나 기능을 언급하나 핵심이 빈약하고 구체적인 내용이 없다.",
            "2": "핵심 기능은 설명하나 구조·흐름 설명이 피상적이거나 일부 부정확하다.",
            "3": "핵심 기능과 구조를 대체로 정확히 설명한다.",
            "4": "구조·의존관계·설계 의도까지 근거를 들어 설명한다.",
        },
        display_order=1,
    ),
    ScoreCriterionSpec(
        score_key="technical_reasoning",
        label_ko="기술적 근거",
        description="기술 선택과 구현 방식에 대해 근거를 들어 설명하는가.",
        rubric={
            "0": "질문을 받았지만 이유를 말하지 않거나(방식만 말하는 경우 포함) 모른다고 답한다.",
            "1": "이유를 말하지만 '편해서·많이 써서' 같이 내용이 없는 수준이다.",
            "2": "근거는 제시하나 대안과의 비교가 없거나 피상적이다.",
            "3": "대안을 인지하고 선택 이유를 합리적으로 설명한다.",
            "4": "트레이드오프를 구체적으로 비교하고 한계까지 인지하고 있다.",
        },
        display_order=2,
    ),
    ScoreCriterionSpec(
        score_key="problem_solving",
        label_ko="문제 해결 능력",
        description="개발 중 마주친 문제를 어떻게 식별하고 해결했는가.",
        rubric={
            "0": "질문을 받았지만 문제 상황을 구체적으로 떠올리지 못한다.",
            "1": "문제 상황만 말하거나, 구체적인 원인·방법 없이 해결했다고만 말한다.",
            "2": "해결했다고 말하며 원인이나 방법을 언급하나 모호하거나 일부만 설명한다.",
            "3": "문제 원인을 진단하고 해결한 과정을 구체적으로 설명한다.",
            "4": "여러 대안을 검토한 근거와 재발 방지까지 설명한다.",
        },
        display_order=3,
    ),
    ScoreCriterionSpec(
        score_key="communication",
        label_ko="의사소통 명확성",
        description="질문 의도를 파악하고 답변을 논리적으로 구성해 전달하는가.",
        rubric={
            "0": "질문과 무관한 답변을 하거나 의미를 파악하기 어렵다.",
            "1": "질문의 일부에만 답하고 핵심이 불분명하다.",
            "2": "질문에는 답하나 설명 순서가 뒤섞여 이해하기 어렵다.",
            "3": "질문 의도에 맞춰 논리적 순서로 답변한다.",
            "4": "핵심을 먼저 제시하고 근거를 명확히 구조화해 설명한다.",
        },
        display_order=4,
    ),
    ScoreCriterionSpec(
        score_key="contribution_clarity",
        label_ko="기여도 명확성",
        description="본인이 실제로 수행한 역할과 기여 범위를 구체적으로 설명하는가.",
        rubric={
            "0": "질문을 받았지만 본인이 한 일을 말하지 못한다.",
            "1": "참여했다고만 말하고 팀 성과와 본인 기여를 구분하지 못한다.",
            "2": "본인이 한 일은 말하나 범위와 결과가 불명확하다.",
            "3": "본인이 담당한 부분과 그 근거를 구체적으로 설명한다.",
            "4": "협업 지점과 단독 기여를 명확히 구분해 설명한다.",
        },
        display_order=5,
    ),
    ScoreCriterionSpec(
        score_key="company_job_fit",
        label_ko="직무 적합성",
        description="지원 공고의 요구사항과 본인 경험을 얼마나 연결해 설명하는가.",
        rubric={
            "0": (
                "질문을 받았지만 무엇을 했는지 말하지 않거나"
                "(경험이 있다는 말만 하는 경우 포함) 모른다고 답한다."
            ),
            "1": "요구사항이나 경험 중 하나만 구체적으로 언급한다.",
            "2": "요구사항과 경험을 둘 다 언급하며 연결하나 근거가 빈약하거나 일반론에 그친다.",
            "3": "요구사항과 본인 경험을 구체적 사례로 연결한다.",
            "4": "요구사항별로 대응하는 경험과 한계까지 균형 있게 설명한다.",
        },
        display_order=6,
    ),
)


async def seed_score_criteria(
    session: AsyncSession, criteria: Iterable[ScoreCriterionSpec] = SCORE_CRITERIA
) -> None:
    """score_criteria 를 upsert 한다. 재실행해도 같은 결과다(idempotent).

    label_ko/description/rubric/display_order 는 팀 검수에 따라 갱신될 수 있으므로
    존재하는 행이라도 값이 다르면 덮어쓴다 — prompt_versions 와 달리 충돌로 막지 않는다.
    is_active 는 신규 행에만 FALSE 로 넣고 충돌 시 건드리지 않아,
    검수 후 활성화한 값을 되돌리지 않는다.
    따라서 이미 활성인 행의 rubric 은 새 초안으로 바뀐 채 활성 상태를 유지한다.
    """
    for criterion in criteria:
        await session.execute(
            text(
                """
                INSERT INTO score_criteria
                    (score_key, label_ko, description, rubric, display_order, is_active)
                VALUES
                    (:score_key, :label_ko, :description,
                     CAST(:rubric AS jsonb), :display_order, FALSE)
                ON CONFLICT (score_key) DO UPDATE SET
                    label_ko = EXCLUDED.label_ko,
                    description = EXCLUDED.description,
                    rubric = EXCLUDED.rubric,
                    display_order = EXCLUDED.display_order,
                    updated_at = now()
                """
            ),
            {
                "score_key": criterion.score_key,
                "label_ko": criterion.label_ko,
                "description": criterion.description,
                "rubric": _as_jsonb(criterion.rubric),
                "display_order": criterion.display_order,
            },
        )


def _as_jsonb(rubric: dict[str, str]) -> str:
    """asyncpg 는 dict 를 JSONB 로 자동 변환하지 않는다.

    JSON 문자열로 넘기고 SQL 에서 CAST 한다.
    """
    return json.dumps(rubric, ensure_ascii=False)


__all__ = ["LEVEL_SCORES", "SCORE_CRITERIA", "ScoreCriterionSpec", "seed_score_criteria"]
