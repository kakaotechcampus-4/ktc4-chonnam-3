"""확정 질문의 원문과 별개로 음성 합성용 문장을 준비한다."""

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.features.interview.speech_address import iter_address_spans
from app.features.interview.speech_paths import iter_file_spans
from app.integrations.tts.pronunciation import (
    COMBINING_MARKS,
    LATIN_CHARACTERS,
    SpeechFragment,
    is_latin_name,
)

QUESTION_SPEECH_VERSION = "question-speech.v4"
_DIGITS = "영일이삼사오육칠팔구"
_UNITS = {"ms": " 밀리초", "%": " 퍼센트"}
_TERMS = {
    "inference": "인퍼런스",
    "manager": "매니저",
    "cache": "캐시",
    "retry": "리트라이",
    "api": "에이피아이",
    "http": "에이치티티피",
    "jwt": "제이더블유티",
    "cpu": "씨피유",
    "gpu": "지피유",
    "get": "겟",
    "post": "포스트",
    "url": "유알엘",
    "user_id": "유저 아이디",
    "retry_count": "리트라이 카운트",
    "eventservice": "이벤트 서비스",
    "request_id": "리퀘스트 아이디",
    "requestid": "리퀘스트 아이디",
    "overwrite": "오버라이트",
    "writeback": "라이트백",
    "yaml": "야믈",
    "redis": "레디스",
    "postgresql": "포스트그레에스큐엘",
    "github actions": "깃허브 액션즈",
    "docker": "도커",
    "c#": "씨샵",
    ".net": "닷넷",
    "node.js": "노드 제이에스",
    "python": "파이썬",
    "'_'": "밑줄 기호",
    "'/'": "슬래시 기호",
}
_TERM = re.compile(
    rf"(?<![{LATIN_CHARACTERS}{COMBINING_MARKS}0-9_./-])(?:"
    + "|".join(map(re.escape, sorted(_TERMS, key=len, reverse=True)))
    + rf")(?![{LATIN_CHARACTERS}{COMBINING_MARKS}0-9_]|[./-][{LATIN_CHARACTERS}0-9_])",
    re.ASCII | re.IGNORECASE,
)
_SLASH_TERMS = {"read/write": "리드와 라이트", "ci/cd": "씨아이 씨디", "a/b": "에이비"}
_SLASH_TERM = re.compile(
    r"(?<![A-Za-z0-9_./\\-])(?:read[ \t]*/[ \t]*write|ci[ \t]*/[ \t]*cd|a[ \t]*/[ \t]*b)"
    r"(?![A-Za-z0-9_/\\-]|\.[A-Za-z0-9_])",
    re.ASCII | re.IGNORECASE,
)
_AB_TEST_CONTEXT = re.compile(r"`?\s*(?:테스트|실험|test\b|experiment\b)", re.IGNORECASE)
_TECH_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_])(?P<label>C\+\+|Python |HTTP/|[pv])"
    r"(?P<value>[0-9]+(?:\.[0-9]+)*)(?![A-Za-z0-9_]|\.\d)"
)
_CPP = re.compile(r"(?<![A-Za-z0-9_])C\+\+(?![A-Za-z0-9_+])")
_FRACTION = re.compile(r"(?<![A-Za-z0-9_./])([0-9]+)/([0-9]+)(?![A-Za-z0-9_./])")
_STATUS_CONTEXT = re.compile(
    r"(?:HTTP|응답|상태\s*코드|오류\s*코드|에러\s*코드)\s*(?:응답\s*)?(?:상태\s*코드\s*)?$",
    re.IGNORECASE,
)
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.])(?<!\d,)([+−-]?)([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
    r"(?:\.([0-9]+))?(ms|%)?(?![A-Za-z0-9_%]|[.,][0-9])"
)
_VARIABLES = {"a": "에이", "b": "비", "x": "엑스", "y": "와이"}
_OPERATOR = re.compile(r"(?<![A-Za-z0-9_])([abxy])\s*(>=|!=|&&)\s*([abxy])(?![A-Za-z0-9_])")
_EXPRESSION = {
    ">=": "{left}가 {right} 이상인",
    "!=": "{left}가 {right}와 같지 않은",
    "&&": "{left}와 {right}가 모두 참인",
}
_CLOSED = {"와": "과", "를": "을", "는": "은", "가": "이"}
_OPEN = {closed: opened for opened, closed in _CLOSED.items()}
_OPAQUE = re.compile(
    r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://[^\s가-힣`<>\"']*"
    r"|(?:[A-Za-z]:[\\/]|[/\\]|www\.)[A-Za-z0-9._~%+:/\\-][^\s가-힣`<>\"']*"
    r"|(?<![A-Za-z0-9_])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+"
    r"|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\s*=\s*[^\s가-힣]+"
    r"|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z0-9_]+\]|\([A-Za-z0-9_, ]*\))"
    r"|(?P<fence>`{2,})[\s\S]*?(?:(?P=fence)(?!`)|\Z)|`[^`\n]*(?:`|(?=\n|\Z))"
    r'|(?<![A-Za-z0-9])"(?:[^"\\\n]|\\.)*(?:"|(?=\n|\Z))'
    r"|(?<![A-Za-z0-9])'(?:[^'\\\n]|\\.)*(?:'|(?=\n|\Z))"
    r"|“[^”\n]*(?:”|\Z)|‘[^’\n]*(?:’|\Z)"
)
_SHELL_OR_SECRET = re.compile(
    r"(?:^|\s)(?:\$\s+|(?:sudo|curl|wget|git|kubectl|chmod|rm|cat|ls|bash|powershell|npm|npx|pip)"
    r"\s+[a-z-]|docker\s+(?:run|exec|build|pull|push)\b)"
    r"|(?:^|\s)--[A-Za-z][A-Za-z0-9_-]*|\$\(|\s[|<>]\s"
    r"|\b(?:authorization\s*:\s*bearer|bearer\s+[A-Za-z0-9]|"
    r"[A-Za-z_]*(?:password|secret|token|key)\s*[:=]|"
    r"(?:api\s+key|access\s+token|refresh\s+token)\s*[:=]|"
    r"(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{16,})",
    re.IGNORECASE,
)
_NAME_LETTERS = LATIN_CHARACTERS + COMBINING_MARKS
_NAME = (
    rf"[{LATIN_CHARACTERS}][{_NAME_LETTERS}0-9]*"
    rf"(?:['’][{LATIN_CHARACTERS}][{_NAME_LETTERS}]*)?"
    rf"(?:[_.-][{_NAME_LETTERS}0-9]+)*"
)
_FRAGMENT = re.compile(
    rf"(?<![{_NAME_LETTERS}0-9_.+@/:\\=%-])"
    + _NAME
    + r"(?:[ \t]+"
    + _NAME
    + rf"){{0,3}}(?![{_NAME_LETTERS}0-9_+@/:\\=%-]|\.[{_NAME_LETTERS}0-9_])"
)
_NAME_TOKEN = re.compile(_NAME)
_READABLE_QUOTE = re.compile(_NAME + r"(?:[ \t]+" + _NAME + r"){0,3}\Z")
_QUOTE_END = {"`": "`", "'": "'", '"': '"', "“": "”", "‘": "’"}
_PROSE_QUOTE = re.compile(rf"[{_NAME_LETTERS}가-힣0-9\s.,!?…%+−'’-]+\Z")
_LITERAL_QUOTE_CONTEXT = re.compile(r"문자열|리터럴|정규식|CSV|JSON|기호|표기|쉼표|구분자")
_CODE_AFTER_QUOTE = re.compile(r"\s*(?:이라는|라는)?\s*코드")
_SECRET_NAME = re.compile(r"(?:^|[_-])(?:secret|password|token|key)(?:$|[_-])", re.I)
_MAX_FRAGMENTS = 12
_PRONUNCIATION = re.compile(r"[가-힣]+(?: [가-힣]+)*\Z")
_MARKER = re.compile(r"\ue000([0-9]+)\ue001")
_LEXICAL = re.compile(r"\ue100([0-9]+)\ue101")
_LEXICAL_PARTICLE = re.compile(r"(\ue100([0-9]+)\ue101)(와|과|를|을|는|은|가|이)(?![가-힣])")
_PARTICLE = re.compile(r"(\ue000[0-9]+\ue001)(와|과|를|을|는|은|가|이)(?![가-힣])")
_LIST_AND = re.compile(r"(\ue000[0-9]+\ue001) 및 (?=(\ue000[0-9]+\ue001))")
_NUMERIC_LIST = re.compile(
    r"(?<=[이가] )(\ue000[0-9]+\ue001),\s+"
    r"(?=[가-힣]+(?: [가-힣]+){0,3}[이가] (\ue000[0-9]+\ue001)(?:이?라는|인)\s)"
)


@dataclass(frozen=True, slots=True)
class PreparedSpeech:
    fragments: tuple[SpeechFragment, ...]
    _template: str
    _fallbacks: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return self._render(self._fallbacks)

    def with_pronunciations(self, pronunciations: tuple[str, ...]) -> str:
        if len(pronunciations) != len(self.fragments) or any(
            len(value) > 80 or not _PRONUNCIATION.fullmatch(value) for value in pronunciations
        ):
            raise ValueError("Invalid speech pronunciations")
        return self._render(pronunciations)

    def _render(self, values: tuple[str, ...]) -> str:
        def particle(match: re.Match[str]) -> str:
            last = values[int(match[2])][-1:]
            suffix = match[3]
            if last and "가" <= last <= "힣":
                alternatives = _CLOSED if (ord(last) - ord("가")) % 28 else _OPEN
                suffix = alternatives.get(suffix, suffix)
            return match[1] + suffix

        template = _LEXICAL_PARTICLE.sub(particle, self._template)
        return _LEXICAL.sub(lambda match: values[int(match[1])], template)


def _integer(digits: str) -> str:
    if len(digits) > 4 or (len(digits) > 1 and digits[0] == "0"):
        return " ".join(_DIGITS[int(digit)] for digit in digits)
    words = []
    for digit, unit in zip(digits.zfill(4), ("천", "백", "십", ""), strict=True):
        if digit != "0":
            words.append(("" if unit and digit == "1" else _DIGITS[int(digit)]) + unit)
    return "".join(words) or "영"


def _contrasting_names(text: str) -> set[str]:
    spellings: dict[str, set[str]] = {}
    for match in _NAME_TOKEN.finditer(text):
        canonical = re.sub(r"[_.-]", "", match[0]).casefold()
        spellings.setdefault(canonical, set()).add(match[0])
    return {name for names in spellings.values() if len(names) > 1 for name in names}


def _case_prefix(name: str) -> str:
    if name.islower():
        return "소문자로 쓴 "
    if name.isupper():
        return "모든 글자가 대문자인 "
    positions = [index + 1 for index, char in enumerate(name) if char.isupper()]
    if positions == [1]:
        return "첫 글자가 대문자인 "
    labels = "과 ".join(_integer(str(position)) + " 번" for position in positions)
    return "대문자 위치가 " + labels + "인 "


def _local_spans(
    text: str,
    resolve: Callable[[str, str, str], str],
    structured: set[tuple[int, int]],
) -> Iterator[tuple[int, int, str]]:
    for span in iter_address_spans(text, resolve=resolve):
        structured.add((span[0], span[1]))
        yield span

    contrast_ids = bool(re.search(r"\brequest_id\b", text) and re.search(r"\brequestId\b", text))
    contrasted = _contrasting_names(text)
    for match in _TERM.finditer(text):
        word = match[0].lower()
        spoken = _TERMS[word]
        if contrast_ids and word in {"request_id", "requestid"}:
            spoken = {
                "request_id": "밑줄로 이은 리퀘스트 아이디",
                "requestid": "아이를 대문자로 이어 쓴 리퀘스트 아이디",
            }.get(word, spoken)
        elif match[0] in contrasted:
            spoken = _case_prefix(match[0]) + spoken
        yield *match.span(), spoken
    # 같은 범위를 파일로도 해석할 수 있는 .NET 같은 등록 기술명은 기존 발음을 우선한다.
    for start, end, spoken in iter_file_spans(text, resolve=resolve):
        structured.add((start, end))
        if re.match(r"""[`"'”’]?\s*파일""", text[end:]):
            spoken = spoken.removesuffix(" 파일")
        yield start, end, spoken
    for match in _SLASH_TERM.finditer(text):
        literal = "".join(match[0].split())
        word = literal.lower()
        if word == "a/b" and literal != "A/B" and not _AB_TEST_CONTEXT.match(text, match.end()):
            yield *match.span(), match[0]
            continue
        yield *match.span(), _SLASH_TERMS[word]
    for match in _CPP.finditer(text):
        yield *match.span(), "씨플러스플러스"
    for match in _TECH_NUMBER.finditer(text):
        label, value = match.groups()
        prefix = {
            "C++": "씨플러스플러스",
            "Python ": "파이썬",
            "HTTP/": "에이치티티피 버전",
            "p": "피",
            "v": "브이",
        }[label]
        yield *match.span(), prefix + " " + " 점 ".join(map(_integer, value.split(".")))
    for match in _FRACTION.finditer(text):
        left, right = match.groups()
        status_codes = len(left) == len(right) == 3 and left[0] in "12345" and right[0] in "12345"
        if status_codes or not right.strip("0"):
            if status_codes and _STATUS_CONTEXT.search(
                text[max(0, match.start() - 32) : match.start()]
            ):
                spoken = f"{_integer(left)}와 {_integer(right)}"
            else:
                spoken = f"{_integer(left)} 슬래시 {_integer(right)}"
        else:
            spoken = f"{_integer(right)}분의 {_integer(left)}"
        yield *match.span(), spoken
    for match in _NUMBER.finditer(text):
        sign, integer, decimal, unit = match.groups()
        spoken = {"+": "플러스 ", "-": "마이너스 ", "−": "마이너스 ", "": ""}[sign]
        spoken += _integer(integer.replace(",", ""))
        if decimal is not None:
            spoken += " 점 " + " ".join(_DIGITS[int(digit)] for digit in decimal)
        yield *match.span(), spoken + _UNITS.get(unit or "", "")
    for match in _OPERATOR.finditer(text):
        left, operator, right = match.groups()
        spoken = _EXPRESSION[operator].format(left=_VARIABLES[left], right=_VARIABLES[right])
        end = match.end()
        if not re.match(r"`?\s+조건(?:[가-힣]|\b)", text[end:]):
            spoken += " 조건"
        yield match.start(), end, spoken
