import pytest

from app.features.interview.speech_address import iter_address_spans
from app.features.interview.speech_paths import iter_file_spans


def test_address_resolver_receives_only_unknown_name_parts() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role, fallback))
        return "이름"

    spans = list(
        iter_address_spans(
            "`https://Acme.com:8443/api/v1/ProjectService/42?customKey=SecretValue#SecretAnchor`",
            resolve=resolve,
        )
    )

    assert [(name, role) for name, role, _ in names] == [
        ("Acme", "domain"),
        ("ProjectService", "path"),
        ("customKey", "identifier"),
    ]
    assert all(fallback for _, _, fallback in names)
    assert "포트 팔사사삼" in spans[0][2]
    assert "브이일 이름 사십이" in spans[0][2]


def test_domain_suffix_keeps_confirmed_joined_pronunciation() -> None:
    spans = list(
        iter_address_spans(
            "https://EXAMPLE.COM/api/v1/users",
            resolve=lambda name, role, fallback: fallback,
        )
    )

    assert "이그잼플 닷컴" in spans[0][2]


def test_mixed_address_components_resolve_names_and_keep_numbers_local() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return {"Service": "서비스", "ProjectService": "프로젝트서비스"}[name]

    spans = list(
        iter_address_spans(
            "https://Service42.com/api/v1/ProjectService42/003?version=v1.10",
            resolve=resolve,
        )
    )

    assert names == [("Service", "domain"), ("ProjectService", "path")]
    assert "서비스 사십이 닷컴" in spans[0][2]
    assert "브이일 프로젝트서비스 사십이 공 공 삼" in spans[0][2]
    assert "버전 값 브이 일 점 십" in spans[0][2]


def test_encoded_bytes_and_query_values_never_reach_resolver() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return fallback

    list(
        iter_address_spans(
            "https://example.com/api/v1/files/%2F?tag=UnknownValue#UnknownAnchor",
            resolve=resolve,
        )
    )

    assert names == []


def test_resolved_path_names_keep_separator_distinctions_when_comparing_paths() -> None:
    def resolve(name: str, role: str, fallback: str) -> str:
        return {"custom": "커스텀", "route": "라우트"}.get(name, fallback)

    speech = list(
        iter_address_spans(
            "`/api/custom-route`와 `/api/custom_route` 및 `/api/custom/route/`의 "
            "경로 차이를 비교해 설명하세요.",
            resolve=resolve,
        )
    )

    assert "커스텀 하이픈 라우트" in speech[0][2]
    assert "커스텀 밑줄 라우트" in speech[1][2]
    assert "뒤에 슬래시" in speech[2][2]


@pytest.mark.parametrize(
    "text",
    ["`/telemetry/ingest`를 설명하세요.", "/telemetry/ingest 엔드포인트를 설명하세요."],
)
def test_unknown_relative_endpoint_uses_context_and_name_resolver(text: str) -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role))
        return {"telemetry": "텔레메트리", "ingest": "인제스트"}[name]

    spans = list(iter_address_spans(text, resolve=resolve))

    assert names == [("telemetry", "path"), ("ingest", "path")]
    assert "텔레메트리 아래 인제스트" in spans[0][2]


def test_unqualified_endpoint_and_file_paths_do_not_reach_address_resolver() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append(name)
        return fallback

    for text in (
        "/telemetry/ingest를 설명하세요.",
        "`/var/log/app.log` 파일을 설명하세요.",
        "`/telemetry/ingest` 파일을 설명하세요.",
        "실험군 비율 1/2를 설명하세요.",
    ):
        assert list(iter_address_spans(text, resolve=resolve)) == []
    assert names == []


def test_default_relative_endpoint_keeps_spelling_boundary() -> None:
    spans = list(iter_address_spans("`/telemetry/ingest`"))

    assert "다음 구간" in spans[0][2]


def test_file_resolver_receives_complete_alphabetic_name_parts() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append((name, role, fallback))
        return {"CustomDir": "커스텀디렉터리", "RequestHandler": "리퀘스트핸들러", "cfg": "컨피그"}[
            name
        ]

    spans = list(iter_file_spans("`CustomDir/RequestHandler.cfg`", resolve=resolve))

    assert [(name, role) for name, role, _ in names] == [
        ("CustomDir", "path"),
        ("RequestHandler", "file"),
        ("cfg", "extension"),
    ]
    assert spans[0][2] == "커스텀디렉터리 폴더의 리퀘스트핸들러 컨피그 파일"


def test_unknown_basename_extension_requires_file_context_code_or_a_path() -> None:
    assert list(iter_file_spans("report.customext 값을 설명하세요.")) == []
    assert list(iter_file_spans("report.customext 파일을 설명하세요."))
    assert list(iter_file_spans("`report.customext` 파일을 설명하세요."))
    assert list(iter_file_spans("config/report.customext 파일을 설명하세요."))


def test_file_resolver_does_not_receive_known_names_or_url_content() -> None:
    names = []

    def resolve(name: str, role: str, fallback: str) -> str:
        names.append(name)
        return fallback

    list(iter_file_spans("src/main.py config/settings.yaml", resolve=resolve))
    list(iter_file_spans("`https://example.com/PrivateDir/SecretFile.cfg`", resolve=resolve))
    assert names == []


@pytest.mark.parametrize("iterator", [iter_address_spans, iter_file_spans])
def test_resolver_exceptions_reach_the_caller(iterator) -> None:
    def resolve(name: str, role: str, fallback: str) -> str:
        raise ValueError("resolver failure")

    with pytest.raises(ValueError, match="resolver failure"):
        list(iterator("https://custom.com/api/custom `custom/custom.cfg`", resolve=resolve))
