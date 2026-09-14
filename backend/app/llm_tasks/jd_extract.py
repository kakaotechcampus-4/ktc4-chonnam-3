"""공고 → jd_requirements 추출. category = required / preferred / responsibility.
원티드는 requirements / preferred_points / main_tasks 가 이미 나뉘어 오고 skill_tags 가
tech_tags 원천이므로 LLM 추측이 불필요하다. 상한 20개.

확정본 §3 jd_requirements / task-09

1차는 원티드(구조화된 어댑터 응답)만 지원하므로 이 파일은 LLM 을 호출하지 않는다 —
`PostingContent.is_structured`가 항상 True 인 입력만 들어온다(제너릭 어댑터는 fetch 단계에서
이미 unsupported_site 로 실패한다). 비구조화 입력(2차, LLM 기반 추출)은 아직 구현하지 않았다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.jd.base import PostingContent

MAX_REQUIREMENTS = 20

# FE·BE 합의: category CHECK 값. 순서가 display_order 우선순위와도 일치한다
# (필수 → 우대 → 주요업무 순으로 화면에 그룹핑돼 보이는 게 자연스럽다는 판단).
_CATEGORY_ORDER: tuple[tuple[str, str], ...] = (
    ("requirements", "required"),
    ("preferred_points", "preferred"),
    ("main_tasks", "responsibility"),
)


@dataclass(frozen=True, slots=True)
class JdRequirementDraft:
    """`jd_requirements` 행 하나를 만들기 위한 값 객체. DB 세션을 모른다 —
    실제 INSERT 는 `features/analysis/pipeline/steps/jd_extract.py` 가 담당한다."""

    category: str
    """"required" | "preferred" | "responsibility" — CHECK 제약과 동일."""

    text: str
    display_order: int
    tech_tags: list[str]


class JdExtractionError(Exception):
    """`not_a_job_posting` / `extraction_failed` 등 — docs/error-reasons.md ④.
    현재는 원티드 구조화 입력만 다루므로 requirements/preferred_points/main_tasks 가
    전부 비어 있을 때만 발생한다 (LLM 판정이 필요한 2차 케이스는 아직 없음)."""

    code: str

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def build_requirement_drafts(posting: PostingContent) -> list[JdRequirementDraft]:
    """구조화된 `PostingContent`에서 `jd_requirements` 초안 목록을 만든다.

    우대(preferred_points)를 필수(requirements)로 뒤섞지 않도록 어댑터가 준 카테고리
    구분을 그대로 유지한다 — 우리 쪽에서 텍스트 내용을 보고 재분류하지 않는다
    (W5 완료 기준: "우대를 필수로 바꾸지 않을 것").

    tech_tags 는 원티드가 공고 전체 단위로만 주므로(문장별 태깅 없음), 모든 행에
    동일한 `posting.skill_tags`를 붙인다 — 레포 매칭(task-10)은 문장 단위가 아니라
    공고 전체 vs 레포 tech_stack 비교라 이 정도 해상도로 충분하다.
    """
    if not posting.is_structured:
        # 2차: 비구조화 텍스트를 LLM 으로 분류하는 경로. 아직 미구현.
        raise JdExtractionError(
            "extraction_failed", "구조화되지 않은 공고 추출은 아직 지원하지 않음"
        )

    drafts: list[JdRequirementDraft] = []
    for field_name, category in _CATEGORY_ORDER:
        for text in getattr(posting, field_name):
            if len(drafts) >= MAX_REQUIREMENTS:
                return drafts
            drafts.append(
                JdRequirementDraft(
                    category=category,
                    text=text,
                    display_order=len(drafts),
                    tech_tags=list(posting.skill_tags),
                )
            )

    if not drafts:
        raise JdExtractionError("extraction_failed", "요구사항 0건")

    return drafts
