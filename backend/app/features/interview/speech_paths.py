"""파일 경로의 구성 요소를 한국어로 읽는다."""

import re
from collections.abc import Callable, Iterator
from itertools import groupby

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
_DIGITS = dict(zip("0123456789", "영 일 이 삼 사 오 육 칠 팔 구".split(), strict=True))
_NAMES = {
    "README": "리드미",
    "app": "앱",
    "backend": "백엔드",
    "ci": "씨아이",
    "config": "컨피그",
    "docs": "독스",
    "fixtures": "픽스처",
    "frontend": "프론트엔드",
    "github": "깃허브",
    "index": "인덱스",
    "log": "로그",
    "main": "메인",
    "package": "패키지",
    "settings": "세팅스",
    "src": "에스알씨",
    "test": "테스트",
    "tests": "테스츠",
    "var": "바",
    "workflows": "워크플로스",
    "workspace": "워크스페이스",
}
_EXTENSIONS = {
    "csv": "씨에스브이",
    "js": "제이에스",
    "json": "제이슨",
    "log": "로그",
    "md": "엠디",
    "py": "파이",
    "sql": "에스큐엘",
    "toml": "톰엘",
    "ts": "티에스",
    "txt": "티엑스티",
    "yaml": "야믈",
    "yml": "와이엠엘",
}

_SEPARATOR = r"[/\\]"
_HANGUL = r"가-힣\u1100-\u11ff\u3131-\u318e"
_ATOM = rf"[{LATIN_CHARACTERS}{COMBINING_MARKS}{_HANGUL}0-9_-]+"
_LATIN_WORD = rf"[{LATIN_CHARACTERS}][{LATIN_CHARACTERS}{COMBINING_MARKS}]*"
_NAME_COMPONENT = re.compile(rf"{_LATIN_WORD}|[{_HANGUL}]+|[0-9]+|[-_.]")
_QUOTED = re.compile(r"(?<![\\`])(?P<quote>[`\"'])(?P<value>[^`\"'\r\n]+)(?P=quote)(?!`)")
_PARTICLE = re.compile(
    r"(?:으로부터|에서는|에서|으로|까지|부터|와|과|로|에|은|는|을|를|이|가|의|도|만)(?![가-힣])"
)
_FILE_CONTEXT = re.compile(r"\s*파일(?:명)?(?=$|[\s.,!?을를은는이가의에로와과])")


def _path_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![\w{COMBINING_MARKS}./\\:%-])"
        rf"(?P<root>[A-Za-z]:{_SEPARATOR}|(?:\.\.?{_SEPARATOR})+|{_SEPARATOR})?"
        rf"(?P<directories>(?:\.?{name}(?:\.{name})*{_SEPARATOR})*)"
        rf"(?:(?P<stem>\.?{name}(?:\.{name})*)\."
        rf"(?P<extension>[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9]{{1,12}})"
        rf"|(?P<hidden>\.[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9_-]+))"
        rf"(?![{LATIN_CHARACTERS}{COMBINING_MARKS}0-9_/\\%-]|\.[\w{COMBINING_MARKS}])"
    )


_PATH = _path_pattern(_ATOM)
_QUOTED_PATH = _path_pattern(rf"{_ATOM}(?: +{_ATOM})*")


def _file_matches(text: str) -> list[tuple[int, int, re.Match[str]]]:
    quoted = list(_QUOTED.finditer(text))
    quoted_paths = []
    candidates: list[tuple[int, int, re.Match[str], bool]] = []
    for quote in quoted:
        match = _QUOTED_PATH.fullmatch(quote["value"])
        if match is not None:
            start = quote.start("value")
            candidates.append((start, quote.end("value"), match, True))
            quoted_paths.append(quote)
    for match in _PATH.finditer(text):
        if any(
            quote.start("value") <= match.start() < quote.end("value") for quote in quoted_paths
        ):
            continue
        candidates.append((*match.span(), match, False))

    matches = []
    for start, end, match, is_quoted in candidates:
        extension = match["extension"] or ""
        if extension and not any(is_latin_name(char) for char in extension):
            # v1.10 같은 버전 표기를 숫자 확장자를 가진 파일로 바꾸지 않는다.
            continue
        stem = match["stem"] or match["hidden"]
        suffix = text[end:]
        file_context = bool(_FILE_CONTEXT.match(suffix))
        if not (
            match["root"]
            or match["directories"]
            or is_quoted
            or stem.startswith(".")
            or any(char.isdigit() for char in extension)
            or file_context
        ):
            continue
        if suffix and suffix[0].isalnum() and not (_PARTICLE.match(suffix) or file_context):
            continue
        matches.append((start, end, match))
    return sorted(matches, key=lambda item: item[0])


def _spelled_name(name: str) -> str:
    labels = []
    for part in _NAME_COMPONENT.findall(name):
        if part in _NAMES:
            labels.append(_NAMES[part])
        elif part in {"-", "_", "."}:
            labels.append({"-": "하이픈", "_": "밑줄", ".": "닷"}[part])
        elif part.isdigit():
            labels.extend(_DIGITS[char] for char in part)
        elif not is_latin_name(part):
            labels.append(part)
        else:
            for uppercase, letters in groupby(part, key=str.isupper):
                if uppercase:
                    labels.append("대문자")
                labels.extend(spell_letter(char, _LETTERS) for char in letters)
    return " ".join(label for label in labels if label)


def _spoken_name(
    name: str, resolve: ResolveName | None, *, role: str, preserve_separators: bool
) -> str:
    parts: list[str] = []
    for part in _NAME_COMPONENT.findall(name):
        if part == "-" and not parts and not preserve_separators and re.match(r"-[0-9]", name):
            parts.append("마이너스")
            continue
        if part in {"_", "-"} and not preserve_separators and re.search(r"\w", name):
            continue
        # 일반 낭독의 미등록 이름은 Google의 원문 발음을 사용한다.
        fallback = (
            part
            if is_latin_name(part) and part not in _NAMES and not preserve_separators
            else _spelled_name(part)
        )
        if resolve is not None and is_latin_name(part) and part not in _NAMES:
            parts.append(resolve(part, role, fallback))
        else:
            parts.append(fallback)
    return " ".join(parts)


def _spoken_root(root: str) -> str:
    if root == "/":
        return "루트의 "
    if root == "\\":
        return "드라이브 루트의 "
    if root[1:2] == ":":
        return f"{_LETTERS[root[0].lower()]} 드라이브의 "
    parts = [part for part in re.split(_SEPARATOR, root) if part]
    return "".join("현재 폴더 기준 " if part == "." else "상위 폴더 기준 " for part in parts)


def iter_file_spans(
    text: str, *, resolve: ResolveName | None = None
) -> Iterator[tuple[int, int, str]]:
    matches = _file_matches(text)
    preserve_separators = requires_separator_names(
        text, (text[start:end] for start, end, _ in matches)
    )
    for start, end, match in matches:
        root = match["root"] or ""
        directories = [name for name in re.split(_SEPARATOR, match["directories"]) if name]
        prefix = _spoken_root(root)
        if directories:
            prefix += (
                " 아래 ".join(
                    _spoken_name(
                        name, resolve, role="path", preserve_separators=preserve_separators
                    )
                    for name in directories
                )
                + " 폴더의 "
            )
        stem = _spoken_name(
            match["stem"] or match["hidden"],
            resolve,
            role="file",
            preserve_separators=preserve_separators,
        )
        extension_name = match["extension"] or ""
        extension = _EXTENSIONS.get(extension_name.lower(), "" if not extension_name else None)
        if extension is None:
            extension = _spoken_name(
                extension_name, resolve, role="extension", preserve_separators=preserve_separators
            )
        spoken = f"{prefix}{stem}" + (f" {extension}" if extension else "") + " 파일"
        yield start, end, spoken
