import pytest

from app.features.interview.speech_address import iter_address_spans
from app.features.interview.speech_paths import iter_file_spans


def resolve_name(name: str, role: str, fallback: str) -> str:
    return {
        "user": "유저",
        "profile": "프로파일",
        "custom": "커스텀",
        "route": "라우트",
        "data": "데이터",
    }.get(name, fallback)


@pytest.mark.parametrize(
    ("source", "spoken_name"),
    [
        ("/api/v1/user_profile 경로로 요청을 보내세요.", "유저 프로파일"),
        ("`/api/v1/user-profile` 경로로 요청을 보내세요.", "유저 프로파일"),
        ("https://example.com/api/custom-route/ 경로로 요청을 보내세요.", "커스텀 라우트"),
    ],
)
def test_ordinary_route_reads_names_without_separator_labels(source: str, spoken_name: str) -> None:
    spans = list(iter_address_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    assert spoken_name in spans[0][2]
    assert all(label not in spans[0][2] for label in ("밑줄", "하이픈", "슬래시"))


def test_ordinary_route_keeps_hierarchy_without_reading_slashes() -> None:
    spans = list(
        iter_address_spans("`/api/custom/route/` 경로로 요청을 보내세요.", resolve=resolve_name)
    )

    assert "커스텀 아래 라우트" in spans[0][2]
    assert "슬래시" not in spans[0][2]


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("`/api/custom_route` 경로의 '_' 기호가 사용되는 이유를 설명하세요.", "밑줄"),
        ("`/api/custom-route` 경로의 '-' 기호가 사용되는 이유를 설명하세요.", "하이픈"),
        ("`/api/users/` 경로의 후행 슬래시가 사용되는 이유를 설명하세요.", "슬래시"),
    ],
)
def test_route_keeps_separator_when_the_symbol_is_the_question(source: str, label: str) -> None:
    spans = list(iter_address_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    assert label in spans[0][2]


def test_route_comparison_keeps_hyphen_and_underscore_distinct() -> None:
    spans = list(
        iter_address_spans(
            "`/api/custom-route`와 `/api/custom_route`의 경로 차이를 비교해 설명하세요.",
            resolve=resolve_name,
        )
    )

    assert len(spans) == 2
    assert "커스텀 하이픈 라우트" in spans[0][2]
    assert "커스텀 밑줄 라우트" in spans[1][2]


def test_route_comparison_keeps_trailing_slash_distinct() -> None:
    spans = list(
        iter_address_spans(
            "`/api/users`와 `/api/users/`의 경로 차이를 비교해 설명하세요.",
            resolve=resolve_name,
        )
    )

    assert len(spans) == 2
    assert "슬래시" not in spans[0][2]
    assert "슬래시" in spans[1][2]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("`config/user_profile.yaml` 파일을 읽으세요.", "컨피그 폴더의 유저 프로파일 야믈 파일"),
        ("`config/custom-route.json` 파일을 읽으세요.", "컨피그 폴더의 커스텀 라우트 제이슨 파일"),
        (
            "`user_data/custom-route/user_profile.yaml` 파일을 읽으세요.",
            "유저 데이터 아래 커스텀 라우트 폴더의 유저 프로파일 야믈 파일",
        ),
    ],
)
def test_ordinary_file_keeps_folders_and_extension_without_separator_labels(
    source: str, expected: str
) -> None:
    spans = list(iter_file_spans(source, resolve=resolve_name))

    assert len(spans) == 1
    assert spans[0][2] == expected


def test_file_comparison_keeps_hyphen_and_underscore_distinct() -> None:
    spans = list(
        iter_file_spans(
            "`config/user-profile.yaml`와 `config/user_profile.yaml`의 파일명 차이를 설명하세요.",
            resolve=resolve_name,
        )
    )

    assert len(spans) == 2
    assert "유저 하이픈 프로파일 야믈 파일" in spans[0][2]
    assert "유저 밑줄 프로파일 야믈 파일" in spans[1][2]


def test_file_keeps_underscore_when_the_symbol_is_the_question() -> None:
    spans = list(
        iter_file_spans(
            "`config/user_profile.yaml` 파일명의 '_' 기호가 사용되는 이유를 설명하세요.",
            resolve=resolve_name,
        )
    )

    assert "유저 밑줄 프로파일 야믈 파일" in spans[0][2]


def test_natural_route_keeps_domain_version_and_query_value_meaning() -> None:
    spans = list(
        iter_address_spans(
            "https://example.com/api/v1/user_profile?version=v1.10&sort=created_at "
            "주소로 요청을 보내세요.",
            resolve=resolve_name,
        )
    )

    speech = spans[0][2]
    assert "이그잼플 닷컴" in speech
    assert "브이일" in speech
    assert "유저 프로파일 경로에" in speech
    assert "버전 값 브이 일 점 십" in speech
    assert "소트 값 크리에이티드 밑줄 앳" in speech


def test_dashboard_context_does_not_make_a_route_a_symbol_question() -> None:
    spans = list(
        iter_address_spans(
            "대시보드에서 /api/user_profile 경로를 호출하세요.", resolve=resolve_name
        )
    )

    assert "유저 프로파일" in spans[0][2]
    assert "밑줄" not in spans[0][2]


def test_dash_question_still_reads_the_hyphen_name() -> None:
    spans = list(
        iter_address_spans("/api/user-profile 경로의 대시를 설명하세요.", resolve=resolve_name)
    )

    assert "유저 하이픈 프로파일" in spans[0][2]


def test_negative_number_in_route_keeps_its_sign() -> None:
    spans = list(iter_address_spans("/api/-10 경로를 호출하세요.", resolve=resolve_name))

    assert "마이너스 십" in spans[0][2]


def test_negative_number_in_file_keeps_its_sign() -> None:
    spans = list(iter_file_spans("config/-10.json 파일을 읽으세요.", resolve=resolve_name))

    assert "마이너스 일 영" in spans[0][2]


def test_comma_separated_routes_keep_different_spellings_distinct() -> None:
    spans = list(
        iter_address_spans(
            "/api/user-profile, /api/user_profile 경로를 순서대로 호출하세요.",
            resolve=resolve_name,
        )
    )

    assert len(spans) == 2
    assert "유저 하이픈 프로파일" in spans[0][2]
    assert "유저 밑줄 프로파일" in spans[1][2]
