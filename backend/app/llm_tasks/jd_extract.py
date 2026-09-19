"""공고 → jd_requirements 초안. API category와 DB requirement_type을 구분한다.
원티드는 requirements / preferred_points / main_tasks 가 이미 나뉘어 오고 skill_tags 가
tech_tags 원천이므로 LLM 추측 불필요. 상한 20개

확정본 §3 jd_requirements / task-09

1차는 원티드 구조화 필드를 규칙으로 변환하며 LLM을 호출하지 않는다.
요구사항 필드가 없는 입력은 jd_extraction_failed로 실패한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.integrations.jd.base import PostingContent

MAX_REQUIREMENTS = 20
JdCategory = Literal["required", "preferred", "responsibility"]

# API 표시 순서이자 원문 출처. DB에는 category 대신 requirement_type을 사용한다.
_CATEGORY_SOURCES: dict[JdCategory, str] = {
    "required": "requirements",
    "preferred": "preferred_points",
    "responsibility": "main_tasks",
}


@dataclass(frozen=True, slots=True)
class JdRequirementDraft:
    """요구사항 초안. DB 세션과 API 직렬화는 호출부가 담당한다.

    저장 시 ``requirement_type``과 ``source_field``를 읽어 분류와 출처를 보존한다.
    두 값은 계산 속성이므로 ``dataclasses.asdict()`` 결과에는 포함되지 않는다.
    ``category``는 API 표시용이므로 DB requirement_type에 그대로 넣지 않는다.
    """

    category: JdCategory
    """API 표시 분류. 주요 업무는 responsibility로 표시한다."""

    text: str
    display_order: int
    tech_tags: list[str]

    @property
    def requirement_type(self) -> str:
        """DB/AI 분류. 주요 업무만으로 필수·우대 여부를 추측하지 않는다."""
        return {
            "required": "required",
            "preferred": "preferred",
            "responsibility": "unknown",
        }[self.category]

    @property
    def source_field(self) -> str:
        """Wanted 원문 필드. unknown만으로 주요 업무를 역추론하지 않는다."""
        return _CATEGORY_SOURCES[self.category]


class JdExtractionError(Exception):
    """구조화된 공고에서 요구사항 초안을 만들 수 없을 때 발생.

    현재 추출 함수는 `jd_extraction_failed` 코드로 이 예외를 발생시킨다.
    """

    code: str

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def build_requirement_drafts(posting: PostingContent) -> list[JdRequirementDraft]:
    """구조화된 `PostingContent`에서 `jd_requirements` 초안 목록을 만듦

    우대(preferred_points)를 필수(requirements)로 뒤섞지 않도록 어댑터가 준 카테고리
    구분을 그대로 유지 — 우리 쪽에서 텍스트 내용을 보고 재분류하지 않음
    (W5 완료 기준: "우대를 필수로 바꾸지 않을 것")

    tech_tags 는 원티드가 공고 전체 단위로만 주므로(문장별 태깅 없음), 모든 행에
    동일한 `posting.skill_tags`를 붙인다. 이 태그는 공고 전체의 기술 목록이며,
    각 문장에서 해당 기술을 직접 요구한다는 뜻은 아니다.
    """
    if not posting.is_structured:
        # 구조화된 요구사항 필드가 하나도 없으면 결정적으로 실패한다.
        raise JdExtractionError(
            "jd_extraction_failed", "구조화되지 않은 공고 추출은 아직 지원하지 않음"
        )

    drafts: list[JdRequirementDraft] = []
    for category, field_name in _CATEGORY_SOURCES.items():
        for text in getattr(posting, field_name):
            if len(drafts) >= MAX_REQUIREMENTS:
                return drafts
            drafts.append(
                JdRequirementDraft(
                    category=category,
                    text=text,
                    display_order=len(drafts),
                    # 한 초안의 태그 수정이 다른 초안이나 원본 공고에 전파되지 않게 복사한다.
                    tech_tags=list(posting.skill_tags),
                )
            )

    if not drafts:
        raise JdExtractionError("jd_extraction_failed", "요구사항 0건")

    return drafts
