"""6개 루브릭 시드 (label_ko 포함).

docs/db-schema.md / task-03

score_key 는 shared/enums.py ScoreKey 와 1:1 이며 CHECK 제약(SCORE_KEYS)이 이를 보장한다.
세부 기준 문구는 평가 담당 자료 보강에 따라 갱신될 수 있어 rubric 은 JSONB 로 둔다.

★ 미검수 초안이다. is_active=FALSE 로 시드하며 활성화는 검수 후 별도로 한다(ADR 0018).
★ rubric 1~4단계를 공개 점수 0~100 으로 바꾸는 기준은 아직 정해지지 않았다(ADR 0010).
  이 기준이 확정되기 전에는 활성화하거나 리포트 프롬프트가 환산하게 두지 않는다.
★ 1단계는 "질문을 받고도 답하지 못함"만 뜻한다. 질문하지 않았거나 근거가 부족한 항목은
  점수가 아니라 미관찰이므로 어느 단계에도 대응하지 않는다(task-11).
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ScoreCriterionSpec:
    """score_criteria 한 행. rubric 은 {"1": "...", ...} 형태의 구간별 기준이다."""

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
            "1": "질문을 받았지만 프로젝트의 목적이나 핵심 기능을 설명하지 못한다.",
            "2": "표면적인 설명은 하지만 구조나 핵심 흐름을 잘못 이해하고 있다.",
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
            "1": "질문을 받았지만 왜 그렇게 구현했는지 근거를 제시하지 못한다.",
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
            "1": "질문을 받았지만 문제 상황을 구체적으로 떠올리지 못한다.",
            "2": "문제는 있었으나 해결 과정 설명이 모호하다.",
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
            "1": "답변했으나 질문과 무관하거나 논리적 흐름이 없다.",
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
            "1": "질문을 받았지만 팀 전체 성과와 본인 기여를 구분하지 못한다.",
            "2": "본인 역할을 언급하나 구체적 범위가 불명확하다.",
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
            "1": "질문을 받았지만 공고 요구사항과 본인 경험을 연결하지 못한다.",
            "2": "일부 연결하나 근거가 빈약하거나 일반론에 그친다.",
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
    is_active 는 FALSE 로만 넣고 충돌 시 건드리지 않아, 검수 후 활성화한 값을 되돌리지 않는다.
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


__all__ = ["SCORE_CRITERIA", "ScoreCriterionSpec", "seed_score_criteria"]
