import pytest

from app.features.interview.speech_paths import iter_file_spans


def resolve_name(name: str, role: str, fallback: str) -> str:
    return {
        "env": "엔브",
        "deploy": "디플로이",
        "archive": "아카이브",
        "z": "제트",
        "Program": "프로그램",
        "Files": "파일스",
        "data": "데이터",
        "home": "홈",
        "café": "카페",
        "cafe\u0301": "카페",
        "profile": "프로파일",
        "report": "리포트",
        "customext": "커스텀익스텐션",
    }.get(name, fallback)


@pytest.mark.parametrize(
    ("source", "literal", "expected"),
    [
        (".env 파일을 확인하세요.", ".env", "닷 엔브 파일"),
        ("`.env.deploy` 파일을 확인하세요.", ".env.deploy", "닷 엔브 디플로이 파일"),
        ("config/.env 파일을 확인하세요.", "config/.env", "컨피그 폴더의 닷 엔브 파일"),
        (
            "`../config/.env.deploy` 파일을 확인하세요.",
            "../config/.env.deploy",
            "상위 폴더 기준 컨피그 폴더의 닷 엔브 디플로이 파일",
        ),
    ],
)
def test_dotfiles_keep_the_hidden_prefix_and_full_filename(
    source: str, literal: str, expected: str
) -> None:
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    start, end, speech = spans[0]
    assert source[start:end] == literal
    assert speech == expected


@pytest.mark.parametrize("literal", ["archive.7z", "config/archive.7z"])
def test_digit_prefixed_extensions_keep_the_number_and_resolve_the_letters(literal: str) -> None:
    source = literal + " 파일을 확인하세요."
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    start, end, speech = spans[0]
    assert source[start:end] == literal
    assert "아카이브 칠 제트 파일" in speech


@pytest.mark.parametrize("quote", ['"', "'", "`"])
def test_quoted_windows_path_keeps_the_drive_and_spaced_directory(quote: str) -> None:
    literal = r"C:\Program Files\app_data\settings.yaml"
    source = quote + literal + quote + " 파일을 확인하세요."
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    start, end, speech = spans[0]
    assert source[start:end] == literal
    assert speech == "씨 드라이브의 프로그램 파일스 아래 앱 데이터 폴더의 세팅스 야믈 파일"


def test_quoted_unix_path_keeps_korean_spaces_and_latin_filename() -> None:
    literal = "/home/작업 자료/café 보고서.yaml"
    source = f"`{literal}` 파일을 확인하세요."
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    start, end, speech = spans[0]
    assert source[start:end] == literal
    assert speech == "루트의 홈 아래 작업 자료 폴더의 카페 보고서 야믈 파일"


def test_korean_directories_and_filenames_do_not_reach_the_latin_resolver() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return resolve_name(name, role, fallback)

    source = "프로젝트/설정.yaml 파일과 `프로젝트/café_보고서.yaml` 파일을 확인하세요."
    spans = list(iter_file_spans(source, resolve=resolve))

    assert len(spans) == 2
    assert spans[0][2] == "프로젝트 폴더의 설정 야믈 파일"
    assert spans[1][2] == "프로젝트 폴더의 카페 보고서 야믈 파일"
    assert names == [("café", "file")]


@pytest.mark.parametrize("name", ["café", "cafe\u0301"])
def test_accented_latin_filename_reaches_resolver_without_truncation(name: str) -> None:
    names = []

    def resolve(value: str, role: str, fallback: str) -> str:
        names.append((value, role))
        return resolve_name(value, role, fallback)

    source = f"`src/{name}.py` 파일을 확인하세요."
    spans = list(iter_file_spans(source, resolve=resolve))

    assert len(spans) == 1
    assert source[spans[0][0] : spans[0][1]] == f"src/{name}.py"
    assert spans[0][2] == "에스알씨 폴더의 카페 파이 파일"
    assert names == [(name, "file")]


@pytest.mark.parametrize("name", ["café", "cafe\u0301"])
def test_accented_latin_filename_keeps_original_fallback_without_resolver(name: str) -> None:
    spans = list(iter_file_spans(f"`src/{name}.py` 파일을 확인하세요."))

    assert len(spans) == 1
    assert spans[0][2] == f"에스알씨 폴더의 {name} 파이 파일"


def test_unicode_file_comparison_keeps_separator_distinctions() -> None:
    spans = list(
        iter_file_spans(
            "`프로젝트/café_profile.yaml`와 `프로젝트/café-profile.yaml`의 "
            "파일명 차이를 설명하세요.",
            resolve=resolve_name,
        )
    )

    assert len(spans) == 2
    assert "카페 밑줄 프로파일 야믈 파일" in spans[0][2]
    assert "카페 하이픈 프로파일 야믈 파일" in spans[1][2]


def test_pure_numeric_version_is_not_classified_as_a_file_extension() -> None:
    assert list(iter_file_spans("`v1.10` 버전을 설명하세요.")) == []


def test_unknown_unquoted_basename_without_file_context_is_not_rewritten() -> None:
    assert list(iter_file_spans("report.customext 값을 확인하세요.")) == []


@pytest.mark.parametrize(
    ("source", "literal", "expected"),
    [
        ("report.customext 파일을 확인하세요.", "report.customext", "리포트 커스텀익스텐션 파일"),
        ("package.json파일을 확인하세요.", "package.json", "패키지 제이슨 파일"),
        ("report.customext 파일명을 설명하세요.", "report.customext", "리포트 커스텀익스텐션 파일"),
    ],
)
def test_explicit_file_context_recognizes_an_unquoted_basename(
    source: str, literal: str, expected: str
) -> None:
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    start, end, speech = spans[0]
    assert source[start:end] == literal
    assert speech == expected
