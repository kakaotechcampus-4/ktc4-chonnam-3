"""외부 실행 질의의 보수적 필터. 통과가 모든 개인정보 제거를 보장하지는 않는다."""

import re
import unicodedata

SENSITIVE_QUERY = re.compile(
    r"\b[a-z][a-z0-9+.-]*://|www\.|\bBearer\b|\b(?:api[_ -]?key|password|secret[_ -]?key)\s*[:=]|"
    r"\b(?:sk-|tvly-)[A-Za-z0-9_-]{8,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|```|"
    # 전화번호와 같은 형태인 주문번호도 차단할 수 있다. 위험 batch 전체를 보내지 않는다.
    r"(?<!\d)(?:\+82[- ]?0?|0)(?:1[016789]|2|[3-6][1-5])[- .]?\d{3,4}[- .]?\d{4}(?!\d)|"
    r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)",
    re.IGNORECASE,
)


class ExternalQueryError(ValueError):
    """외부·로그에 원문을 넣지 않는 고정 사유다."""


def canonical_external_query(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ExternalQueryError("invalid_query")
    try:
        if len(value.encode("utf-8")) > 4096:
            raise ExternalQueryError("invalid_query")
    except UnicodeError:
        raise ExternalQueryError("invalid_query") from None
    # strip 전에 검사하여 바깥 줄바꿈·제어문자를 제거하는 우회를 허용하지 않는다.
    if SENSITIVE_QUERY.search(value) or any(
        unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in value
    ):
        raise ExternalQueryError("unsafe_external_query")
    return value.strip()
