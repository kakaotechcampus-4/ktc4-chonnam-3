import pytest

from app.features.interview.speech_address import iter_address_spans


def test_www_address_reads_its_real_host_without_inventing_a_scheme() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return {"orbital": "오르비탈", "profile": "프로파일"}[name]

    source = "www.orbital.dev/api/user_profile 경로를 설명하세요."
    spans = list(iter_address_spans(source, resolve=resolve))

    assert len(spans) == 1
    assert source[spans[0][0] : spans[0][1]] == "www.orbital.dev/api/user_profile"
    assert spans[0][2] == "더블유더블유더블유 닷 오르비탈 닷 데브의 에이피아이 유저 프로파일"
    assert names == [("orbital", "domain"), ("profile", "path")]


@pytest.mark.parametrize(
    ("source", "literal", "spoken"),
    [
        (
            "https://example.com/사용자_프로필 경로를 설명하세요.",
            "https://example.com/사용자_프로필",
            "사용자 프로필",
        ),
        (
            "https://example.com/사용자_프로필을 설명하세요.",
            "https://example.com/사용자_프로필을",
            "사용자 프로필을",
        ),
        (
            "https://example.com/마을 경로를 설명하세요.",
            "https://example.com/마을",
            "마을",
        ),
        (
            "https://example.com/마을 설명을 계속하세요.",
            "https://example.com/마을",
            "마을",
        ),
    ],
)
def test_hangul_path_is_read_locally_and_keeps_its_boundary(
    source: str, literal: str, spoken: str
) -> None:
    def reject_hangul(name: str, role: str, fallback: str) -> str:
        raise AssertionError("한글 이름을 발음 모델에 전달하면 안 된다")

    spans = list(iter_address_spans(source, resolve=reject_hangul))

    assert len(spans) == 1
    assert source[spans[0][0] : spans[0][1]] == literal
    assert spans[0][2] == "에이치티티피에스 이그잼플 닷컴의 " + spoken


@pytest.mark.parametrize(
    ("literal", "names"),
    [
        ("https://München.com/café_데이터", [("München", "domain"), ("café", "path")]),
        (
            "www.münchen.com/cafe\u0301_데이터",
            [("münchen", "domain"), ("café", "path")],
        ),
    ],
)
def test_latin_names_reach_resolver_whole_and_hangul_stays_local(
    literal: str, names: list[tuple[str, str]]
) -> None:
    observed = []

    def resolve(name: str, role: str, fallback: str) -> str:
        observed.append((name, role))
        return {"münchen": "뮌헨", "café": "카페"}[name.casefold()]

    spans = list(iter_address_spans(literal + " 경로를 설명하세요.", resolve=resolve))

    assert len(spans) == 1
    assert observed == names
    assert "뮌헨 닷컴의 카페 데이터" in spans[0][2]


def test_unicode_fallback_spells_latin_letters_without_an_index_error() -> None:
    spans = list(iter_address_spans("https://münchen.com/café 경로를 설명하세요."))

    assert len(spans) == 1
    assert "씨 에이 에프 이" in spans[0][2]
    assert "café" not in spans[0][2]


def test_unicode_query_values_and_fragments_never_reach_the_resolver() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return {"café": "카페", "owner": "오너"}[name]

    spans = list(
        iter_address_spans(
            "https://example.com/사용자/café?owner=München_private%2F42#café_hidden "
            "주소를 설명하세요.",
            resolve=resolve,
        )
    )

    assert len(spans) == 1
    assert names == [("café", "path"), ("owner", "identifier")]
    assert "퍼센트 이 에프" in spans[0][2]
    assert "밑줄" in spans[0][2]


@pytest.mark.parametrize(
    ("suffix", "value"),
    [
        ("?owner=마을", "마을"),
        ("#마을", "마을"),
        ("?owner=에서는", "에서는"),
        ("#에서는", "에서는"),
    ],
)
def test_hangul_query_or_fragment_is_not_mistaken_for_a_korean_particle(
    suffix: str, value: str
) -> None:
    literal = "https://example.com/사용자" + suffix
    source = literal + " 설명을 계속하세요."
    spans = list(iter_address_spans(source))

    assert len(spans) == 1
    assert source[spans[0][0] : spans[0][1]] == literal
    assert value in spans[0][2]


@pytest.mark.parametrize(
    "literal",
    [
        "www.-bad.com/api/user_profile",
        "www.orbital..dev/api/user_profile",
        "www.orbital.dev:0/api/user_profile",
        "www.orbital.dev:65536/api/user_profile",
        "www.orbital.dev@evil.dev/api/user_profile",
        "https://München..com/café",
        "https://-München.com/café",
        "www.orbital.dev/api/a%zz",
        "owner@www.orbital.dev",
        "ftp://www.orbital.dev/private",
        "evilwww.orbital.dev/private",
    ],
)
def test_www_support_does_not_bypass_authority_or_literal_protection(literal: str) -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append(name)
        return fallback

    assert list(iter_address_spans(literal + " 경로를 확인하세요.", resolve=resolve)) == []
    assert names == []


def test_unicode_paths_preserve_ipv6_port_and_local_numbers() -> None:
    def reject_ip(name: str, role: str, fallback: str) -> str:
        raise AssertionError("IP 주소와 숫자를 발음 모델에 전달하면 안 된다")

    spans = list(
        iter_address_spans(
            "https://[2001:db8::1]:8443/api/v1/사용자/003 경로를 설명하세요.",
            resolve=reject_ip,
        )
    )

    assert len(spans) == 1
    assert "포트 팔사사삼" in spans[0][2]
    assert "브이일 사용자 공 공 삼" in spans[0][2]


def test_unicode_route_spelling_comparison_keeps_separator_names() -> None:
    def resolve(name: str, role: str, fallback: str) -> str:
        return {"münchen": "뮌헨", "café": "카페", "data": "데이터"}[name]

    spans = list(
        iter_address_spans(
            "`https://münchen.com/café-data`와 `https://münchen.com/café_data`의 "
            "경로 표기 차이를 설명하세요.",
            resolve=resolve,
        )
    )

    assert len(spans) == 2
    assert "카페 하이픈 데이터" in spans[0][2]
    assert "카페 밑줄 데이터" in spans[1][2]
