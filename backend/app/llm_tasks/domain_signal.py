"""공고 원문 → domain_lead용 category 신호. LLM을 호출하지 않는 규칙 기반 매칭이다.

domain_question_frames의 category 7종(finance/game/travel/shopping/medical/mobility/etc)
중 하나를 고르되, company_name만으로 강제 분류하지 않는다 (W5 완료 기준). 판정에 실제로
쓰인 원문 조각을 `DomainSignalMatch`로 남겨 "왜 이 category인지"를 항상 원문에서 되짚을
수 있게 한다 — frame 문구 자체나 회사명을 근거로 category를 단정하지 않는다.

spec/ai/features/domain-frames.md §선택과 질문 생성 1항:
"service가 검증된 공고·Context의 category를 전달한다. category가 없거나 신뢰할 수 없으면
모델이 산업을 추측하지 않고 etc를 사용한다."

판정 방식은 spec/ai/decisions/0021-domain-category-signal.md를 따른다. 원티드
`company.industry_name`(→ `PostingContent.industry`)은 공고가 아니라 회사 단위 값이라
company_name과 같은 이유로 판정에 쓰지 않는다. `postings.domain_category`에는 판정 결과를
그대로 쓰고 NULL은 "아직 판정하지 않음"에만 남긴다. `matches`는 DB에 저장하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.integrations.jd.base import PostingContent

DomainCategory = Literal["finance", "game", "travel", "shopping", "medical", "mobility", "etc"]

# domain-frames.md의 고정 7종 중 etc를 제외한 6종만 키워드로 매칭 대상이다.
_TEXT_CATEGORIES: tuple[DomainCategory, ...] = (
    "finance",
    "game",
    "travel",
    "shopping",
    "medical",
    "mobility",
)

# 키워드는 "그 도메인 서비스를 다룬다"는 원문 신호만 담는다. 기술 스택명(React 등)이나
# 회사명 패턴은 포함하지 않는다 — company_name 필드 자체를 매칭 대상에서 제외하는 것과
# 같은 이유다. 결제·예약·재고·물류·운송처럼 여러 도메인에 공통으로 나오는 기능 단어도
# 충돌만 만들므로 넣지 않는다.
_CATEGORY_KEYWORDS: dict[DomainCategory, tuple[str, ...]] = {
    "finance": ("금융", "핀테크", "증권", "은행", "보험", "송금", "대출", "자산관리"),
    "game": ("게임", "게이밍", "e스포츠", "MMORPG", "게임 서버"),
    "travel": ("여행", "숙박", "항공", "호텔", "관광"),
    "shopping": ("커머스", "쇼핑", "이커머스", "리테일"),
    "medical": ("의료", "헬스케어", "병원", "건강관리", "제약", "바이오"),
    "mobility": ("모빌리티", "배차", "택시", "차량 호출", "라이더"),
}

# 직무 자체를 설명하는 필드일수록 도메인 신호가 강하다. 우대사항은 "있으면 좋은 경험"이라
# 필수 요건과 같은 가장 낮은 가중치를 준다.
# ponytail: 고정 가중치, 오분류 사례가 쌓이면 0021 범위 안에서 조정
_FIELD_WEIGHTS: dict[str, int] = {
    "position": 3,
    "main_tasks": 2,
    "requirements": 1,
    "preferred_points": 1,
}


@dataclass(frozen=True, slots=True)
class DomainSignalMatch:
    """category 판정에 실제로 쓰인 원문 근거 한 건."""

    source_field: str
    """"position" | "requirements" | "preferred_points" | "main_tasks"."""

    matched_text: str
    """근거가 된 원문 조각 그 자체 (필드 값 또는 한 문장)."""

    keyword: str
    """`matched_text`에서 실제로 찾은 키워드."""


@dataclass(frozen=True, slots=True)
class DomainSignalResult:
    """공고 하나에 대한 domain category 판정."""

    category: DomainCategory
    """신뢰 가능한 단일 신호가 없으면 `etc`."""

    matches: tuple[DomainSignalMatch, ...]
    """판정된 category의 근거. `etc`이면서 `matches`가 비어 있으면 신호 자체가 없었다는
    뜻이고, `matches`가 있는데 `etc`이면 1위 category가 동점이라 고르지 못했다는 뜻이다
    (이때는 동점 category들의 근거를 모두 담는다)."""


def detect_domain_signal(posting: PostingContent) -> DomainSignalResult:
    """`posting`의 원문에서 domain category 신호를 찾는다. 회사 단위 값인
    `posting.company_name`·`posting.industry`는 참조하지 않는다.

    1. `position`·`main_tasks`·`requirements`·`preferred_points` 원문에서 키워드를 찾는다.
    2. category별로 근거 필드의 가중치(`_FIELD_WEIGHTS`)를 합산해 1위가 단독이면 채택한다.
       예: 주요 업무의 "커머스"(2)가 우대사항의 "게임"(1)보다 앞선다.
    3. 1위가 동점이면 어느 쪽인지 추측하지 않고 `etc`다. 신호가 전혀 없어도 `etc`다.
    """
    matches_by_category = _match_text_fields(posting)
    if not matches_by_category:
        return DomainSignalResult(category="etc", matches=())

    scores = {
        category: sum(_FIELD_WEIGHTS[m.source_field] for m in ms)
        for category, ms in matches_by_category.items()
    }
    top = max(scores.values())
    leaders = [c for c, score in scores.items() if score == top]
    if len(leaders) > 1:
        tied = tuple(m for c in leaders for m in matches_by_category[c])
        return DomainSignalResult(category="etc", matches=tied)

    (category,) = leaders
    return DomainSignalResult(category=category, matches=tuple(matches_by_category[category]))


def _match_text_fields(posting: PostingContent) -> dict[DomainCategory, list[DomainSignalMatch]]:
    matches_by_category: dict[DomainCategory, list[DomainSignalMatch]] = {}
    for source_field, text in _iter_text_fields(posting):
        for category in _TEXT_CATEGORIES:
            keyword = next((kw for kw in _CATEGORY_KEYWORDS[category] if kw in text), None)
            if keyword is not None:
                matches_by_category.setdefault(category, []).append(
                    DomainSignalMatch(source_field=source_field, matched_text=text, keyword=keyword)
                )
    return matches_by_category


def _iter_text_fields(posting: PostingContent) -> list[tuple[str, str]]:
    """`industry`·`company_name`을 제외한, 실제 직무 내용이 담긴 원문 필드만 모은다."""
    fields: list[tuple[str, str]] = []
    if posting.position:
        fields.append(("position", posting.position))
    for source_field in ("requirements", "preferred_points", "main_tasks"):
        for text in getattr(posting, source_field):
            fields.append((source_field, text))
    return fields
