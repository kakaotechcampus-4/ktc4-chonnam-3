import pytest

from app.features.interview.question_speech import prepare_question_speech


@pytest.mark.parametrize("name", ["café", "cafe\u0301", "München", "NaïveBayes"])
def test_latin_accents_are_whole_normalized_names(name: str) -> None:
    import unicodedata

    speech = prepare_question_speech(f"{name}를 선택한 이유를 설명하세요.")

    assert tuple(part.text for part in speech.fragments) == (unicodedata.normalize("NFC", name),)
    assert speech.with_pronunciations(("카페",)) == "카페를 선택한 이유를 설명하세요."


@pytest.mark.parametrize("quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
def test_commas_inside_prose_quotes_are_spaces(quotes: tuple[str, str]) -> None:
    left, right = quotes
    speech = prepare_question_speech(f"{left}주시고, 원문만{right}이라는 안내를 설명하세요.")

    assert "주시고 원문만" in speech.text
    assert "," not in speech.text


def test_quoted_prose_preserves_numeric_value_and_normalizes_english() -> None:
    speech = prepare_question_speech('"café를 쓰고, 오류율은 0.05% 미만"을 설명하세요.')

    assert tuple(part.text for part in speech.fragments) == ("café",)
    spoken = speech.with_pronunciations(("카페",))
    assert "카페를 쓰고 오류율은 영 점 영 오 퍼센트 미만" in spoken


def test_english_question_keeps_names_numbers_and_conditions_separate() -> None:
    speech = prepare_question_speech("Explain NimbusQueue with 0.05% errors.")

    assert speech.fragments
    assert any(part.text == "NimbusQueue" for part in speech.fragments)
    assert all("0.05" not in part.text for part in speech.fragments)
    readings = tuple("검증 이름" for _ in speech.fragments)
    assert "영 점 영 오 퍼센트" in speech.with_pronunciations(readings)


def test_english_contraction_is_not_split_at_the_apostrophe() -> None:
    speech = prepare_question_speech("Don't spell café.")

    assert any(part.text == "Don't" for part in speech.fragments)
    assert any("café" in part.text for part in speech.fragments)
    assert all(part.text not in {"Don", "t", "caf"} for part in speech.fragments)


def test_quoted_file_does_not_repeat_the_file_noun() -> None:
    speech = prepare_question_speech(
        '"C:\\Program Files\\user_data\\München.7z" 파일을 설명하세요.'
    )

    assert "파일 파일" not in speech.text


@pytest.mark.parametrize(
    "source",
    [
        '"a,b"와 "ab"라는 문자열의 쉼표 차이를 설명하세요.',
        '"1,250"라는 문자열의 쉼표를 설명하세요.',
    ],
)
def test_literal_string_questions_keep_the_quoted_characters(source: str) -> None:
    assert prepare_question_speech(source).text == source


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ('"config/user_profile.yaml 파일을 읽으세요."라는 안내를 설명하세요.', "profile"),
        ('"https://example.com/café_프로필 경로로 요청하세요."라는 안내를 설명하세요.', "café"),
    ],
)
def test_prose_quotes_with_structured_names_do_not_hide_their_fragments(
    source: str, name: str
) -> None:
    speech = prepare_question_speech(source)

    assert any(fragment.text == name for fragment in speech.fragments)
    assert "_" not in speech.text


@pytest.mark.parametrize(
    "source",
    [
        '"x=1, y=2" 코드를 확인하세요.',
        "`x=1, y=2` 코드를 확인하세요.",
        "```\ncafé, NimbusQueue\n``` 코드를 확인하세요.",
        "git status",
        "api key=private-example",
    ],
)
def test_code_commands_and_values_still_keep_their_original_text(source: str) -> None:
    speech = prepare_question_speech(source)

    assert speech.text == source
    assert speech.fragments == ()
