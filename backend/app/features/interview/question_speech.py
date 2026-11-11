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


def _mask(
    text: str, resolve: Callable[[str, str, str], str]
) -> tuple[str, list[tuple[str, str, bool]]]:
    structured: set[tuple[int, int]] = set()
    known = list(_local_spans(text, resolve, structured))
    recognized: dict[int, set[int]] = {}
    for start, end, _ in known:
        recognized.setdefault(start, set()).add(end)
    opaque = []
    for match in _OPAQUE.finditer(text):
        start, end = match.span()
        literal = match[0]
        balanced_quote = _QUOTE_END.get(literal[:1]) == literal[-1:]
        content = literal[1:-1]
        prose = list(content)
        for left, right, _ in known:
            if start < left <= right < end:
                prose[left - start - 1 : right - start - 1] = " " * (right - left)
        literal_question = _LITERAL_QUOTE_CONTEXT.search(text) or _CODE_AFTER_QUOTE.match(
            text[end:]
        )
        if balanced_quote and (
            (start + 1, end - 1) in structured
            or (
                not literal_question
                and not _SECRET_NAME.search(content)
                and (
                    end - 1 in recognized.get(start + 1, ())
                    or _READABLE_QUOTE.fullmatch(content)
                    or (literal[:1] != "`" and _PROSE_QUOTE.fullmatch("".join(prose)))
                )
            )
        ):
            # 문장 인용부호는 낭독에서 빼고 내부의 숫자·이름은 각 처리 규칙에 맡긴다.
            known.extend(((start, start + 1, ""), (end - 1, end, "")))
            continue
        if any(
            right <= end and not text[right:end].strip(".,)") for right in recognized.get(start, ())
        ):
            continue
        opaque.append((start, end, literal, False))
    candidates = [(start, end, spoken, True) for start, end, spoken in known] + opaque
    candidates.sort(key=lambda span: (span[0], -span[1]))
    segments: list[str] = []
    spans: list[tuple[str, str, bool]] = []
    end = 0
    for start, stop, spoken, adaptable in candidates:
        if start >= end:
            segments.extend((text[end:start], f"\ue000{len(spans)}\ue001"))
            spans.append((text[start:stop], spoken, adaptable))
            end = stop
    segments.append(text[end:])
    return "".join(segments), spans


def _normalize_masked(masked: str, spans: list[tuple[str, str, bool]]) -> str:
    masked = _MARKER.sub(
        lambda match: "" if spans[int(match[1])][1:] == ("", True) else match[0], masked
    )

    def spoken_list(match: re.Match[str]) -> str:
        (left, _, left_known), (_, _, right_known) = (
            spans[int(marker[1:-1])] for marker in match.groups()
        )
        if not left_known or not right_known or left.endswith(("#", "+")):
            return match[0]
        return match[1] + " 그리고 "

    def numeric_list(match: re.Match[str]) -> str:
        indices = (int(marker[1:-1]) for marker in match.groups())
        return (
            match[1] + "이고 "
            if all(_NUMBER.fullmatch(spans[index][0]) for index in indices)
            else match[0]
        )

    def particle(match: re.Match[str]) -> str:
        marker, original = match.groups()
        _, spoken, adaptable = spans[int(marker[1:-1])]
        if not adaptable or not spoken or not "가" <= spoken[-1] <= "힣":
            return match[0]
        alternatives = _CLOSED if (ord(spoken[-1]) - ord("가")) % 28 else _OPEN
        return marker + alternatives.get(original, original)

    masked = re.sub(r"`(\ue000[0-9]+\ue001)`", r"\1", masked)
    masked = _LIST_AND.sub(spoken_list, masked)
    masked = _NUMERIC_LIST.sub(numeric_list, masked)
    masked = _PARTICLE.sub(particle, masked)
    return " ".join(re.sub(r",(?![0-9])", " ", masked).split())


def prepare_question_speech(text: str) -> PreparedSpeech:
    # 명령어나 자격증명 가능성이 있는 문장은 음성 변환 모델에 전달하지 않는다.
    if any(marker in text for marker in ("\ue000", "\ue001", "\ue100", "\ue101")):
        return PreparedSpeech((), text)
    if _SHELL_OR_SECRET.search(text):
        return PreparedSpeech((), text)

    entries: list[tuple[str, str, str, str]] = []
    indices: dict[tuple[str, str, str], int] = {}
    contrasted = _contrasting_names(text)
    current_context = ""

    def safe_context(value: str) -> str:
        value = _MARKER.sub(" 보호된 정보 ", value)
        value = _LEXICAL.sub(" 발음 대상 ", value)
        return " ".join(re.sub(r"[^가-힣\s.,?!…()]", " ", value).split())[:240]

    def spelling_prefix(name: str) -> str:
        if name not in contrasted:
            return ""
        if "_" in name:
            return "밑줄로 구분한 "
        if "-" in name:
            return "하이픈으로 구분한 "
        if "." in name:
            return "점으로 구분한 "
        return _case_prefix(name)

    def resolve(name: str, kind: str, fallback: str) -> str:
        name = unicodedata.normalize("NFC", name)
        if len(name) > 80 or _SECRET_NAME.search(name):
            return fallback
        if len(name) == 1 and kind in {"domain", "path", "file", "extension", "identifier"}:
            return fallback
        if name.isalpha() and name.islower() and len(name) > 24:
            return fallback
        key = (name, kind, current_context)
        if key not in indices:
            if len(entries) == _MAX_FRAGMENTS:
                return fallback
            indices[key] = len(entries)
            entries.append((name, kind, fallback, current_context))
        return spelling_prefix(name) + f"\ue100{indices[key]}\ue101"

    masked, spans = _mask(text, resolve)
    masked = _normalize_masked(masked, spans)

    def restore(piece: str) -> str:
        return _MARKER.sub(lambda match: spans[int(match[1])][1], piece)

    def name_reading(name: str) -> str:
        if _SECRET_NAME.search(name):
            return name
        if name.isupper() or (len(name) <= 5 and sum(char.isupper() for char in name) >= 2):
            kind = "acronym"
        elif "_" in name or (name[:1].islower() and any(char.isupper() for char in name)):
            kind = "identifier"
        else:
            kind = "term"
        if not re.search(r"[0-9_.]", name):
            return resolve(name, kind, name)

        # 이름에 섞인 숫자와 구분자는 모델 출력과 별도로 보존한다.
        pieces = []
        for token in re.findall(rf"[{_NAME_LETTERS}]+|[0-9]+(?:\.[0-9]+)*|[_.-]", name):
            if token[0].isalpha():
                pieces.append(resolve(token, kind, token))
            elif token[0].isdigit():
                pieces.append(" 점 ".join(_integer(part) for part in token.split(".")))
            else:
                pieces.append("닷" if token == "." else "")
        return spelling_prefix(name) + " ".join(piece for piece in pieces if piece)

    def fragment(match: re.Match[str]) -> str:
        nonlocal current_context
        value = match[0]
        words = value.split()
        before = masked[max(0, match.start() - 80) : match.start()]
        after = masked[match.end() : match.end() + 80]
        current_context = safe_context(before + " 현재 발음 대상 " + after)
        try:
            if all(is_latin_name(word) and (word.islower() or word.istitle()) for word in words):
                return resolve(value, "term", value)
            return _NAME_TOKEN.sub(lambda item: name_reading(item[0]), value)
        finally:
            current_context = ""

    masked = _FRAGMENT.sub(fragment, masked)
    context = safe_context(masked)
    template = restore(masked)
    used = list(dict.fromkeys(int(match[1]) for match in _LEXICAL.finditer(template)))
    remap = {old: new for new, old in enumerate(used)}
    template = _LEXICAL.sub(lambda match: f"\ue100{remap[int(match[1])]}\ue101", template)
    fragments = tuple(
        SpeechFragment(entries[index][0], entries[index][1], entries[index][3] or context)
        for index in used
    )
    fallbacks = tuple(entries[index][2] for index in used)
    return PreparedSpeech(fragments, template, fallbacks)
