import pytest

from app.features.interview.question_speech import prepare_question_speech
from app.features.interview.speech_paths import iter_file_spans


@pytest.mark.parametrize(
    ("literal", "spoken"),
    [
        ("UserService.java", "UserService java"),
        ("PaymentGateway.kt", "PaymentGateway kt"),
        ("OrderPolicy.java", "OrderPolicy java"),
        ("café.customext", "café customext"),
    ],
)
def test_unknown_file_names_keep_latin_fallbacks(literal: str, spoken: str) -> None:
    source = f"{literal} 파일을 설명하세요."
    speech = prepare_question_speech(source)

    assert speech.text == f"{spoken} 파일을 설명하세요."
    assert list(iter_file_spans(source))[0][2] == f"{spoken} 파일"


def test_file_case_comparison_survives_equal_model_pronunciations() -> None:
    speech = prepare_question_speech(
        "`UserService.java`와 `userService.java`의 파일명 차이를 설명하세요."
    )
    readings = {"UserService": "유저 서비스", "userService": "유저 서비스", "java": "자바"}

    spoken = speech.with_pronunciations(tuple(readings[item.text] for item in speech.fragments))

    assert "대문자 위치가 일 번과 오 번인 유저 서비스 자바 파일" in spoken
    assert "대문자 위치가 오 번인 유저 서비스 자바 파일" in spoken


def test_known_extension_case_comparison_keeps_its_uppercase_positions() -> None:
    speech = prepare_question_speech("`src/main.py`와 `src/main.PY`의 파일명 차이를 설명하세요.")

    assert speech.fragments == ()
    assert "소문자로 쓴 에스알씨 폴더의 메인 파이 파일" in speech.text
    assert "대문자 위치가 십 번과 십일 번인 에스알씨 폴더의 메인 파이 파일" in speech.text


def test_local_slash_alias_does_not_consume_unknown_name_capacity() -> None:
    names = (
        "NovelAlpha",
        "NovelBeta",
        "NovelGamma",
        "NovelDelta",
        "NovelEpsilon",
        "NovelZeta",
        "NovelEta",
        "NovelTheta",
        "NovelIota",
        "NovelKappa",
        "NovelLambda",
        "NovelMu",
    )
    speech = prepare_question_speech("CI/CD와 " + " 및 ".join(names) + "를 설명하세요.")

    assert tuple(item.text for item in speech.fragments) == names


@pytest.mark.parametrize("separator", ["/", " / "])
@pytest.mark.parametrize(
    ("left", "right", "readings"),
    [
        ("TCP", "IP", ("티씨피", "아이피")),
        ("I", "O", ("아이", "오")),
        ("async", "await", ("어싱크", "어웨이트")),
        ("client", "server", ("클라이언트", "서버")),
        ("writer", "reader", ("라이터", "리더")),
        ("café", "München", ("카페", "뮌헨")),
    ],
)
def test_prose_slash_compounds_resolve_both_names(
    left: str, right: str, readings: tuple[str, str], separator: str
) -> None:
    speech = prepare_question_speech(f"{left}{separator}{right} 구조를 설명하세요.")

    assert tuple(item.text for item in speech.fragments) == (left, right)
    assert speech.text == f"{left} 슬래시 {right} 구조를 설명하세요."
    assert speech.with_pronunciations(readings) == (
        f"{readings[0]} 슬래시 {readings[1]} 구조를 설명하세요."
    )


@pytest.mark.parametrize(
    ("literal", "spoken"),
    [
        ("2024/01/15", "이천이십사 년 일 월 십오 일"),
        ("2024/02/29", "이천이십사 년 이 월 이십구 일"),
        ("2000/12/31", "이천 년 십이 월 삼십일 일"),
    ],
)
def test_full_calendar_dates_are_read_atomically(literal: str, spoken: str) -> None:
    speech = prepare_question_speech(f"{literal}의 날짜를 설명하세요.")

    assert speech.text == f"{spoken}의 날짜를 설명하세요."
    assert speech.fragments == ()


@pytest.mark.parametrize(
    "literal",
    ["2023/02/29", "2024/13/15", "2024/00/15", "2024/01/32", "2024/01/15/2", "01/02"],
)
def test_invalid_or_ambiguous_numeric_slash_tokens_remain_whole(literal: str) -> None:
    source = f"{literal}의 의미를 설명하세요."
    speech = prepare_question_speech(source)

    assert speech.text == source
    assert speech.fragments == ()


@pytest.mark.parametrize(
    "source", ["1/2 날짜를 설명하세요.", "11/12 일자를 확인하세요.", "날짜 4/5를 설명하세요."]
)
def test_date_context_does_not_turn_an_ambiguous_pair_into_a_fraction(source: str) -> None:
    assert prepare_question_speech(source).text == source


@pytest.mark.parametrize(
    "source",
    [
        "`TCP/IP` 문자열을 설명하세요.",
        "'async/await' 문자열의 슬래시 기호를 설명하세요.",
        "async/await 코드를 설명하세요.",
        "client/server 경로를 설명하세요.",
        "`2024/01/15` 문자열을 설명하세요.",
        '"2024/01/15"라는 표기를 설명하세요.',
        "git show client/server",
        "api key=client/server",
    ],
)
def test_slash_literal_path_and_command_boundaries_remain_protected(source: str) -> None:
    speech = prepare_question_speech(source)

    assert speech.text == source
    assert speech.fragments == ()


def test_date_inside_a_url_does_not_become_a_calendar_phrase() -> None:
    speech = prepare_question_speech("https://example.com/api/2024/01/15 주소를 설명하세요.")

    assert "년" not in speech.text
    assert "이천이십사 공 일 십오" in speech.text


@pytest.mark.parametrize(
    ("source", "spoken"),
    [
        ("2/3 확률을 설명하세요.", "삼분의 이 확률을 설명하세요."),
        ("HTTP/1.1을 설명하세요.", "에이치티티피 버전 일 점 일을 설명하세요."),
        ("CI/CD를 설명하세요.", "씨아이 씨디를 설명하세요."),
        ("a/b의 의미를 설명하세요.", "a/b의 의미를 설명하세요."),
    ],
)
def test_established_slash_readings_remain_unchanged(source: str, spoken: str) -> None:
    assert prepare_question_speech(source).text == spoken
