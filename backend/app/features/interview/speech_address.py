"""면접 질문 속 주소의 구조를 살려 읽는다."""

import re
import unicodedata
from collections.abc import Callable, Iterator
from urllib.parse import SplitResult, urlsplit

from app.features.interview.speech_spelling import requires_separator_names
from app.integrations.tts.pronunciation import (
    COMBINING_MARKS,
    LATIN_CHARACTERS,
    is_latin_name,
    spell_letter,
)

type ResolveName = Callable[[str, str, str], str]

_LETTERS = dict(
    zip(
        "abcdefghijklmnopqrstuvwxyz",
        (
            "에이 비 씨 디 이 에프 지 에이치 아이 제이 케이 엘 엠 엔 오 피 큐 알 "
            "에스 티 유 브이 더블유 엑스 와이 제트"
        ).split(),
        strict=True,
    )
)
_DIGITS = "공일이삼사오육칠팔구"
_WORDS = {
    "api": "에이피아이",
    "example": "이그잼플",
    "localhost": "로컬호스트",
    "www": "더블유더블유더블유",
    "com": "컴",
    "org": "오알지",
    "net": "넷",
    "dev": "데브",
    "kr": "케이알",
    "docs": "독스",
    "user": "유저",
    "users": "유저스",
    "read": "리드",
    "write": "라이트",
    "files": "파일스",
    "search": "서치",
    "page": "페이지",
    "limit": "리밋",
    "tag": "태그",
    "yaml": "야믈",
    "empty": "엠티",
    "details": "디테일스",
    "intro": "인트로",
    "orders": "오더스",
    "health": "헬스",
    "status": "스테이터스",
    "version": "버전",
    "sort": "소트",
    "created": "크리에이티드",
    "updated": "업데이티드",
    "at": "앳",
}
_PUNCTUATION = {
    "-": "하이픈",
    "_": "밑줄",
    ".": "점",
    "~": "물결표",
    "/": "슬래시",
    ":": "콜론",
    "@": "앳",
    "!": "느낌표",
    "$": "달러",
    "&": "앰퍼샌드",
    "'": "작은따옴표",
    "(": "여는 괄호",
    ")": "닫는 괄호",
    "*": "별표",
    "+": "플러스",
    ",": "쉼표",
    ";": "세미콜론",
    "=": "등호",
    "?": "물음표",
}
_LATIN_WORD = rf"[{LATIN_CHARACTERS}][{LATIN_CHARACTERS}{COMBINING_MARKS}0-9]*"
_TAIL = rf"[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9가-힣._~%!$&'()*+,;=:@/?#-]*"
_HOST = rf"[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9.-]+"
_ADDRESS = re.compile(
    rf"(?<![{LATIN_CHARACTERS}{COMBINING_MARKS}0-9_:/@.-])"
    rf"(?:(?P<absolute>(?i:https?://)(?:\[[A-Fa-f0-9:.]+\]|{_HOST})(?::[0-9]+)?{_TAIL})"
    rf"|(?P<www>(?i:www\.){_HOST}(?::[0-9]+)?{_TAIL})"
    rf"|(?P<relative>/{_TAIL}))"
)
_LABEL_ATOM = rf"(?:[{LATIN_CHARACTERS}][{COMBINING_MARKS}]*|[0-9])"
_LABEL = re.compile(rf"{_LABEL_ATOM}(?:(?:{_LABEL_ATOM}|-)*{_LABEL_ATOM})?\Z")
_COMPONENT = re.compile(rf"%[A-Fa-f0-9]{{2}}|{_LATIN_WORD}|[0-9]+|[가-힣]+|.")
_BAD_ESCAPE = re.compile(r"%(?![A-Fa-f0-9]{2})")
_PARTICLES = r"으로부터|에서는|에서|으로|까지|부터|와|과|로|에|은|는|을|를|이|가|의|도|만"
_PARTICLE = re.compile(rf"(?:{_PARTICLES})(?![가-힣])")
_ROUTE_CONTEXT = re.compile(r"\s*(?:경로|주소|엔드포인트|라우트)")
_FILE_CONTEXT = re.compile(r"\s*(?:파일|폴더|디렉터리)")
_FILE_ENDING = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,11}\Z")
_PAIR = re.compile(r"`?(?:와|과)\s+`?\Z")


def _digit_names(number: str) -> str:
    return "".join(_DIGITS[int(digit)] for digit in number)


def _number(number: str) -> str:
    if number.startswith("0") or len(number) > 4:
        return " ".join(_digit_names(number))
    words = []
    for digit, unit in zip(number.zfill(4), ("천", "백", "십", ""), strict=True):
        if digit != "0":
            words.append(("" if unit and digit == "1" else _digit_names(digit)) + unit)
    return "".join(words)


def _word(value: str, resolve: ResolveName | None = None, *, role: str = "path") -> str:
    value = unicodedata.normalize("NFC", value)
    if re.fullmatch(r"[가-힣]+", value):
        return value
    local = value.lower() if role == "domain" else value
    if local in _WORDS:
        return _WORDS[local]
    lowercase = value.lower()
    if value[0].isupper() and value[1:].islower() and lowercase in _WORDS:
        return "첫 글자가 대문자인 " + _WORDS[lowercase]
    if re.fullmatch(r"v[0-9]+", value):
        return "브이 " + _number(value[1:])
    if value.isdecimal():
        return _number(value)
    if resolve is not None and re.fullmatch(
        rf"(?=.*[{LATIN_CHARACTERS}])(?=.*[0-9])[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9]+",
        value,
    ):
        return " ".join(
            _word(part, resolve, role=role)
            for part in re.findall(
                rf"[{LATIN_CHARACTERS}][{LATIN_CHARACTERS}{COMBINING_MARKS}]*|[0-9]+", value
            )
        )
    fallback = " ".join(
        ("대문자 " if letter.isupper() else "") + spell_letter(letter, _LETTERS)
        if not letter.isdecimal()
        else _digit_names(letter)
        for letter in local
    )
    if resolve is not None and is_latin_name(value):
        return resolve(value, role, fallback)
    return fallback


def _component(
    value: str,
    resolve: ResolveName | None = None,
    *,
    role: str = "path",
    preserve_separators: bool = True,
) -> str:
    words = []
    for token in _COMPONENT.findall(value):
        if token.startswith("%"):
            # 이스케이프를 풀면 슬래시가 경로 구분자로 바뀔 수 있다.
            words.append(f"퍼센트 {_word(token[1].lower())} {_word(token[2].lower())}")
        elif token[0].isalnum():
            words.append(_word(token, resolve, role=role))
        elif token == "-" and not words and not preserve_separators and re.match(r"-[0-9]", value):
            words.append("마이너스")
        elif (
            token in {"_", "-"}
            and not preserve_separators
            and re.search(rf"[{LATIN_CHARACTERS}0-9가-힣%]", value)
        ):
            continue
        else:
            words.append(_PUNCTUATION.get(token, token))
    return " ".join(words)


def _path_speech(path: str, resolve: ResolveName | None, *, preserve_separators: bool) -> str:
    if path == "/":
        return "루트 슬래시" if preserve_separators else "루트"
    segments = path[1:].split("/")
    trailing_slash = segments[-1] == ""
    if trailing_slash:
        segments.pop()
    words = []
    previous_is_spelled = False
    previous_resolved = False
    for segment in segments:
        is_spelled = is_latin_name(segment) and segment not in _WORDS
        component = (
            _component(segment, resolve, preserve_separators=preserve_separators)
            if segment
            else "빈 구간"
        )
        resolved = resolve is not None and component != _component(
            segment, preserve_separators=preserve_separators
        )
        if is_spelled and previous_is_spelled:
            words.append("아래" if resolved or previous_resolved else "다음 구간")
        if segment == "v1":
            words.append("브이일")
        else:
            words.append(component)
        previous_is_spelled = is_spelled
        previous_resolved = resolved
    spoken = " ".join(words)
    return spoken + " 뒤에 슬래시가 붙은" if trailing_slash and preserve_separators else spoken


def _query_speech(query: str, resolve: ResolveName | None, *, preserve_separators: bool) -> str:
    if not query:
        return "빈 쿼리"
    pairs = []
    for pair in query.split("&"):
        key, equals, value = pair.partition("=")
        if not pair:
            pairs.append("빈 항목")
            continue
        name = (
            _component(key, resolve, role="identifier", preserve_separators=preserve_separators)
            if key
            else "이름 없는"
        )
        if equals and value:
            label = name if key else "이름 없는 항목의"
            pairs.append(f"{label} 값 {_component(value)}")
        elif equals:
            pairs.append(f"값이 비어 있는 {name} 항목")
        else:
            pairs.append(f"값 표기가 없는 {name} 항목")
    if len(pairs) == 1:
        return "쿼리의 " + pairs[0]
    linked = [pair + _particle(pair, "과", "와") for pair in pairs[:-1]]
    if len(pairs) > 2:
        linked[-1] = pairs[-2] + " 그리고"
    return "쿼리의 " + " ".join([*linked, pairs[-1]])
