"""step 7의 기술 관련성 판단. 숫자 점수나 경력·자격 충족을 추정하지 않는다."""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.db.models.posting import JdRequirement


@dataclass(frozen=True)
class TechnologyMatch:
    technologies: tuple[str, ...]
    requirement_ids: tuple[uuid.UUID, ...]

    @property
    def reason(self) -> str | None:
        return "공고와 관련된 기술: " + ", ".join(self.technologies) if self.technologies else None


def match_technologies(
    posting_tags: Iterable[str],
    analysis_tags: Iterable[str],
    requirements: Sequence[JdRequirement],
) -> TechnologyMatch:
    """공고 표기를 유지하면서 공백·대소문자만 정규화해 L1 기술과 비교한다."""
    stack = {_normalize(tag).casefold() for tag in analysis_tags if tag.strip()}
    matched: dict[str, str] = {}
    for raw in posting_tags:
        tag = _normalize(raw)
        if tag and tag.casefold() in stack:
            matched.setdefault(tag.casefold(), tag)
    technologies = tuple(matched.values())
    # requirement.tech_tags는 공고 전체 목록의 복사본일 수 있어 문장 근거로 쓰지 않는다.
    ids = tuple(
        item.id for item in requirements if any(_mentions(item.text, tag) for tag in technologies)
    )
    return TechnologyMatch(technologies, ids)


def _normalize(tag: str) -> str:
    return " ".join(tag.split())


def _mentions(text: str, technology: str) -> bool:
    # Go의 일반 동사 용례를 근거로 삼지 않는다. 모호한 단일 문자도 언어 표기만 인정한다.
    spelling = {"go": "Go", "r": "R", "c": "C"}.get(technology.casefold())
    flags = 0 if spelling is not None else re.IGNORECASE
    token = re.escape(spelling or technology)
    # ASCII 기술명 경계로 JavaScript/C++의 일부 일치를 막되 'C#을' 같은 조사는 허용한다.
    return (
        re.search(r"(?<![a-zA-Z0-9_+#])" + token + r"(?![a-zA-Z0-9_+#])", text, flags) is not None
    )
