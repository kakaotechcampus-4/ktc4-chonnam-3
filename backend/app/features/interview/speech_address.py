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


def _host_speech(hostname: str, resolve: ResolveName | None) -> str:
    if ":" in hostname:
        return _component(hostname)
    labels = hostname.removesuffix(".").split(".")
    spoken = [_component(label, resolve, role="domain") for label in labels]
    if len(labels) > 1 and labels[-1].lower() == "com":
        spoken[-2:] = [spoken[-2] + " 닷컴"]
    return " 닷 ".join(spoken) + (" 끝에 점" if hostname.endswith(".") else "")


def _particle(phrase: str, with_coda: str, without_coda: str) -> str:
    return with_coda if (ord(phrase[-1]) - ord("가")) % 28 else without_coda


def _parse_address(literal: str) -> SplitResult:
    url = urlsplit("//" + literal if literal.casefold().startswith("www.") else literal)
    if url.netloc:
        hostname = url.hostname
        if not hostname or url.username is not None or url.netloc.endswith(":") or url.port == 0:
            raise ValueError("Unsupported authority")
        if ":" not in hostname and not all(
            _LABEL.fullmatch(label)
            for label in unicodedata.normalize("NFC", hostname).removesuffix(".").split(".")
        ):
            raise ValueError("Unsupported hostname")
    return url


def _address_speech(
    literal: str,
    url: SplitResult,
    existing_noun: str,
    resolve: ResolveName | None,
    *,
    preserve_separators: bool,
) -> tuple[str, str, str]:
    origin = ""
    host_speech = ""
    if url.netloc:
        scheme = {"https": "에이치티티피에스", "http": "에이치티티피"}.get(url.scheme, "")
        origin = f"{url.scheme}://{url.netloc.lower()}"
        hostname = url.hostname or ""
        if resolve is not None and ":" not in hostname:
            hostname = url.netloc.partition(":")[0]
        host_speech = f"{scheme} {_host_speech(hostname, resolve)}".strip()
        if url.port is not None:
            host_speech += " 포트 " + _digit_names(url.netloc.rpartition(":")[2])

    has_query = "?" in literal.partition("#")[0]
    has_fragment = "#" in literal
    path = (
        _path_speech(url.path, resolve, preserve_separators=preserve_separators) if url.path else ""
    )
    metadata = []
    if has_query:
        metadata.append(_query_speech(url.query, resolve, preserve_separators=preserve_separators))
    if has_fragment:
        metadata.append(
            "프래그먼트 " + _component(url.fragment) if url.fragment else "빈 프래그먼트"
        )
    if metadata:
        if len(metadata) == 2:
            metadata[0] += _particle(metadata[0], "과", "와")
        metadata[-1] += _particle(metadata[-1], "이", "가")
        prefix = f"{path} 경로에 " if path else ""
        noun = "" if existing_noun == "주소" else " 주소"
        return origin, host_speech, prefix + " ".join(metadata) + " 붙은" + noun
    if existing_noun:
        return origin, host_speech, path
    if re.search(r"[가-힣]\Z", url.path):
        return origin, host_speech, path
    return origin, host_speech, f"{path} 경로" if path else "주소"


def iter_address_spans(
    text: str, *, resolve: ResolveName | None = None
) -> Iterator[tuple[int, int, str]]:
    """확실히 식별된 주소의 원문 범위와 그 범위의 낭독문을 반환한다."""
    addresses = []
    for match in _ADDRESS.finditer(text):
        start, end = match.span()
        quoted = start > 0 and text[start - 1] == "`" and text[end : end + 1] == "`"
        literal = match.group()
        if not quoted:
            # 문장 끝 쉼표와 닫는 괄호는 주소 밖에서 그대로 처리한다.
            while literal.endswith(",") or (
                literal.endswith(")") and literal.count(")") > literal.count("(")
            ):
                literal = literal[:-1]
                end -= 1
            if literal.endswith(".") and re.match(r"\s*\Z", text[end:]):
                literal = literal[:-1]
                end -= 1
            if not _ROUTE_CONTEXT.match(text[end:]) and re.match(r"\s+[가-힣]", text[end:]):
                hangul_tail = re.search(r"[가-힣]+\Z", literal)
                if (
                    hangul_tail
                    and _PARTICLE.fullmatch(hangul_tail[0])
                    and re.fullmatch(
                        rf"[{LATIN_CHARACTERS}0-9]",
                        literal[hangul_tail.start() - 1 : hangul_tail.start()],
                    )
                ):
                    # 라틴 문자·숫자 뒤 독립 조사만 떼어 한글 경로명 자체의 음절을 보존한다.
                    literal = literal[: hangul_tail.start()]
                    end -= len(hangul_tail[0])
        suffix = text[end:]
        if suffix and suffix[0].isalnum() and not _PARTICLE.match(suffix):
            continue
        if suffix.startswith(("[", "\\")) or literal.count("#") > 1 or _BAD_ESCAPE.search(literal):
            continue
        noun = _ROUTE_CONTEXT.match(suffix.removeprefix("`"))
        if match.lastgroup == "relative":
            first = literal[1:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
            if not (first == "api" or quoted or noun):
                continue
            if _FILE_CONTEXT.match(suffix.removeprefix("`")):
                continue
        try:
            url = _parse_address(literal)
        except (KeyError, ValueError):
            continue
        if match.lastgroup == "relative" and _FILE_ENDING.search(url.path):
            continue
        addresses.append((start, end, literal, noun.group().strip() if noun else "", url))

    preserve_separators = requires_separator_names(text, (entry[2] for entry in addresses))
    previous_origin = ""
    previous_end = 0
    for start, end, literal, existing_noun, url in addresses:
        # 이름 보완기의 오류는 호출자가 처리한다. 주소 파싱 오류와 섞어 숨기지 않는다.
        origin, host, details = _address_speech(
            literal,
            url,
            existing_noun,
            resolve,
            preserve_separators=preserve_separators,
        )
        shared_origin = bool(
            origin and origin == previous_origin and _PAIR.fullmatch(text[previous_end:start])
        )
        if not host or (shared_origin and details):
            spoken = details
        else:
            spoken = host + (
                f" {details}" if details == "주소" else f"의 {details}" if details else ""
            )
        yield start, end, spoken
        previous_origin = origin
        previous_end = end
