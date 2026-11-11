"""기호 자체가 질문의 대상일 때만 경로 구분자의 이름을 읽는다."""

import re
from collections.abc import Iterable

_SYMBOL_CONTEXT = re.compile(
    r"밑줄|언더스코어|하이픈|대시(?:를|가|는|의|와|로|란|라고|라는)?(?![가-힣])|"
    r"슬래시|백슬래시|구분자|기호|표기|스펠링|"
    r"특수\s*문자|후행|트레일링"
)
_COMPARISON_CONTEXT = re.compile(r"차이|비교|구별|구분|다른|다르")


def requires_separator_names(text: str, literals: Iterable[str]) -> bool:
    if _SYMBOL_CONTEXT.search(text):
        return True
    variants = set(literals)
    if len(variants) > 1 and _COMPARISON_CONTEXT.search(text):
        return True
    spellings: dict[str, set[str]] = {}
    for literal in variants:
        # 같은 이름의 구분자·대소문자 차이는 조각으로 나누기 전에 보존한다.
        canonical = re.sub(r"[-_/\\]", "", literal).casefold()
        spellings.setdefault(canonical, set()).add(literal)
    return any(len(variants) > 1 for variants in spellings.values())
