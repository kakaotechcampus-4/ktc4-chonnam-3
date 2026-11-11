"""발음 변환에 전달하는 이름과 라틴 문자의 공통 처리."""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field

LATIN_CHARACTERS = r"A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02af\u1e00-\u1eff"
COMBINING_MARKS = r"\u0300-\u036f"


def is_latin_name(value: str) -> bool:
    value = unicodedata.normalize("NFC", value)
    return bool(value) and all(
        char.isalpha() and "LATIN" in unicodedata.name(char, "") for char in value
    )


def spell_letter(value: str, letters: Mapping[str, str]) -> str:
    if unicodedata.combining(value):
        return ""
    bases = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(letters[char] for char in bases if char in letters) or value


@dataclass(frozen=True)
class SpeechFragment:
    text: str = field(repr=False)
    kind: str
    context: str = field(repr=False)
