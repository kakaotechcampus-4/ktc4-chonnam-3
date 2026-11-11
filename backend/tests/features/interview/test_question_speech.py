import pytest

from app.features.interview.question_speech import prepare_question_speech


@pytest.mark.parametrize(
    ("original", "spoken"),
    [
        (
            "inference를 확인해 주시고, 원문만 남겨 주세요.",
            "인퍼런스를 확인해 주시고 원문만 남겨 주세요.",
        ),
        ("C++17과 YAML을 비교하세요.", "씨플러스플러스 십칠과 야믈을 비교하세요."),
        ("C++와 C# 및 .NET을 비교하세요.", "씨플러스플러스와 씨샵 및 닷넷을 비교하세요."),
        (
            "CI / CD와 A / B 테스트에서 Read / Write 요청을 설명하세요.",
            "씨아이 씨디와 에이비 테스트에서 리드와 라이트 요청을 설명하세요.",
        ),
        ("a / b 실험을 설명하세요.", "에이비 실험을 설명하세요."),
        ("a / b와 a/b의 의미를 설명하세요.", "a / b와 a/b의 의미를 설명하세요."),
        (
            "오차 1.50과 -0.25%를 비교하세요.",
            "오차 일 점 오 영과 마이너스 영 점 이 오 퍼센트를 비교하세요.",
        ),
        (
            "HTTP 상태 코드 404/500과 비율 1/2를 설명하세요.",
            "에이치티티피 상태 코드 사백사와 오백과 비율 이분의 일을 설명하세요.",
        ),
        ("404/500을 설명하세요.", "사백사 슬래시 오백을 설명하세요."),
        ("a >= b 조건을 설명하세요.", "에이가 비 이상인 조건을 설명하세요."),
        ("`a != b`를 설명하세요.", "에이가 비와 같지 않은 조건을 설명하세요."),
        ("`settings.yaml` 파일을 설명하세요.", "세팅스 야믈 파일을 설명하세요."),
        (
            "`src/main.py`에서 `config/settings.yaml`을 읽으세요.",
            "에스알씨 폴더의 메인 파이 파일에서 컨피그 폴더의 세팅스 야믈 파일을 읽으세요.",
        ),
        (
            "https://example.com/api/v1/users에 겟 요청을 보내세요.",
            "에이치티티피에스 이그잼플 닷컴의 에이피아이 브이일 유저스 경로에 겟 요청을 보내세요.",
        ),
        (
            "재시도 횟수가 3, 대기 시간이 1,250ms라는 두 조건을 설명하세요.",
            "재시도 횟수가 삼이고 대기 시간이 천이백오십 밀리초라는 두 조건을 설명하세요.",
        ),
    ],
)
def test_prepares_known_speech_without_fragments(original: str, spoken: str) -> None:
    result = prepare_question_speech(original)

    assert result.text == spoken
    assert result.fragments == ()


def test_only_unknown_english_is_replaced() -> None:
    result = prepare_question_speech(
        "circuit breaker를 적용하고, "
        "`https://example.com/api/v1/users?version=v1.10`에 겟 요청을 보내세요."
    )

    assert tuple(fragment.text for fragment in result.fragments) == ("circuit breaker",)
    assert "circuit breaker" in result.text
    assert "서킷 브레이커를 적용하고" in result.with_pronunciations(("서킷 브레이커",))
    assert "버전 값 브이 일 점 십" in result.with_pronunciations(("서킷 브레이커",))


def test_english_question_extracts_words_without_changing_punctuation() -> None:
    result = prepare_question_speech("Explain circuit breaker.")

    assert tuple(part.text for part in result.fragments) == ("Explain circuit breaker",)
    assert result.with_pronunciations(("익스플레인 서킷 브레이커",)) == (
        "익스플레인 서킷 브레이커."
    )


def test_slash_alias_does_not_replace_file_path_segments() -> None:
    result = prepare_question_speech("`src/Read/Write.py` 파일을 설명하세요.")

    assert all(fragment.kind in {"path", "file"} for fragment in result.fragments)
    assert "리드와 라이트" not in result.text
    assert "파이 파일을" in result.text


def test_address_preserves_path_and_query_distinctions() -> None:
    result = prepare_question_speech(
        "`https://example.com/api/v1/user?tag=api&tag=yaml&empty=`와 "
        "`https://example.com/api/v1/users/?empty`의 차이를 설명하세요."
    )

    assert result.fragments == ()
    assert result.text.count("이그잼플 닷컴") == 1
    assert "브이일 유저 경로" in result.text
    assert "브이일 유저스 뒤에 슬래시" in result.text
    assert "태그 값 에이피아이와 태그 값 야믈" in result.text
    assert "값이 비어 있는 엠티 항목" in result.text
    assert "값 표기가 없는 엠티 항목" in result.text


@pytest.mark.parametrize(
    "literal",
    [
        "``circuit breaker``",
        "```\ncircuit breaker\n```",
        "`circuit breaker",
        "http://someone:privatepass@localhost/users",
        "ssh://localhost/privatepath",
        "https://example.com/a%zz",
        "curl --header 'Authorization: Bearer sampletoken' https://localhost",
        "git status",
        "docker run testcontainer",
        "api key=examplekey",
        "handler(secret)",
        "user_token",
        "my-secret-key",
        "private@example.com",
        "opaqueabcdefghijklmnopqrstuvwxy",
    ],
)
def test_does_not_send_unsupported_or_sensitive_literals_as_fragments(literal: str) -> None:
    assert prepare_question_speech(f"{literal}을 확인하세요.").fragments == ()


def test_invalid_pronunciations_are_rejected() -> None:
    result = prepare_question_speech("circuit breaker를 적용하세요.")

    for pronunciations in (
        (),
        ("서킷 브레이커", "임의 문장"),
        ("circuit",),
        ("http://example.com",),
    ):
        with pytest.raises(ValueError):
            result.with_pronunciations(pronunciations)


@pytest.mark.parametrize("name", ["QUIC", "gRPC", "OpenTelemetry", "FastAPI", "FooBarClient"])
def test_new_names_are_candidates_without_dictionary_entries(name: str) -> None:
    result = prepare_question_speech(f"{name}를 선택한 이유를 설명해 주세요.")

    assert tuple(fragment.text for fragment in result.fragments) == (name,)
    assert all(fragment.kind in {"term", "acronym", "identifier"} for fragment in result.fragments)
    assert "선택한 이유" in result.fragments[0].context
    assert name not in result.fragments[0].context
    assert result.with_pronunciations(("퀵",)) == "퀵을 선택한 이유를 설명해 주세요."


@pytest.mark.parametrize("name", ["`OpenTelemetry`", "'FastAPI'", '"gRPC"'])
def test_quoted_single_names_can_be_pronounced(name: str) -> None:
    result = prepare_question_speech(f"{name}의 역할을 설명해 주세요.")

    assert len(result.fragments) == 1
    assert result.with_pronunciations(("새로운 이름",)) == "새로운 이름의 역할을 설명해 주세요."


def test_identifier_numbers_and_versions_are_preserved_outside_model_output() -> None:
    result = prepare_question_speech("OAuth2와 TLS1.3을 비교하고 조건은 변경하지 마세요.")

    assert tuple(fragment.text for fragment in result.fragments) == ("OAuth", "TLS")
    assert result.with_pronunciations(("오어스", "티엘에스")) == (
        "오어스 이와 티엘에스 일 점 삼을 비교하고 조건은 변경하지 마세요."
    )


def test_new_path_names_reach_model_without_exposing_query_values() -> None:
    result = prepare_question_speech(
        "https://nebula.dev/api/v1/stream_ingest?owner=privateaccount#internalsection의 "
        "처리를 설명해 주세요."
    )

    assert {(fragment.text, fragment.kind) for fragment in result.fragments} == {
        ("nebula", "domain"),
        ("stream", "path"),
        ("ingest", "path"),
        ("owner", "identifier"),
    }
    assert all("privateaccount" not in fragment.context for fragment in result.fragments)
    assert all("internalsection" not in fragment.context for fragment in result.fragments)
    readings = {"nebula": "네뷸라", "stream": "스트림", "ingest": "인제스트", "owner": "오너"}
    spoken = result.with_pronunciations(tuple(readings[item.text] for item in result.fragments))
    assert "네뷸라 닷 데브" in spoken
    assert "브이일 스트림 인제스트" in spoken
    assert "밑줄" not in spoken


def test_name_in_a_different_sentence_is_not_a_whole_question_rewrite() -> None:
    result = prepare_question_speech("OpenTelemetry를 쓰되 오류율은 0.05% 미만일 때만 배포하세요.")

    assert tuple(item.text for item in result.fragments) == ("OpenTelemetry",)
    assert result.with_pronunciations(("오픈텔레메트리",)) == (
        "오픈텔레메트리를 쓰되 오류율은 영 점 영 오 퍼센트 미만일 때만 배포하세요."
    )


def test_unknown_identifier_spelling_contrasts_survive_equal_pronunciations() -> None:
    result = prepare_question_speech("foo_bar와 fooBar의 표기 차이를 설명해 주세요.")
    readings = {"foo": "푸", "bar": "바", "fooBar": "푸바"}

    spoken = result.with_pronunciations(tuple(readings[item.text] for item in result.fragments))

    assert "밑줄로 구분한 푸 바" in spoken
    assert "대문자 위치가 사 번인 푸바" in spoken


def test_new_relative_route_and_file_extension_have_structured_name_candidates() -> None:
    route = prepare_question_speech("`/telemetry/ingest` 엔드포인트를 설명해 주세요.")
    file = prepare_question_speech("`src/AuroraClient.avsc` 파일을 설명해 주세요.")

    assert {(item.text, item.kind) for item in route.fragments} == {
        ("telemetry", "path"),
        ("ingest", "path"),
    }
    assert {(item.text, item.kind) for item in file.fragments} == {
        ("AuroraClient", "file"),
        ("avsc", "extension"),
    }


def test_case_only_identifier_comparison_keeps_exact_uppercase_positions() -> None:
    result = prepare_question_speech("requestId와 requestID의 표기 차이를 설명해 주세요.")

    assert result.fragments == ()
    assert "대문자 위치가 팔 번인 리퀘스트 아이디" in result.text
    assert "대문자 위치가 팔 번과 구 번인 리퀘스트 아이디" in result.text


def test_same_spelling_in_different_contexts_gets_separate_readings() -> None:
    result = prepare_question_speech(
        "이력서 resume와 일시 중지 작업의 resume를 구별해 설명해 주세요."
    )

    assert tuple(item.text for item in result.fragments) == ("resume", "resume")
    assert result.fragments[0].context != result.fragments[1].context
    assert result.with_pronunciations(("레주메", "리줌")) == (
        "이력서 레주메와 일시 중지 작업의 리줌을 구별해 설명해 주세요."
    )


@pytest.mark.parametrize("phrase", ["API key rotation", "access token refresh"])
def test_credential_management_terms_are_not_mistaken_for_secret_values(phrase: str) -> None:
    result = prepare_question_speech(f"{phrase}를 도입한 이유를 설명해 주세요.")

    assert result.fragments
    assert "도입한 이유" in result.fragments[0].context


def test_single_letter_path_names_keep_approved_explicit_boundaries() -> None:
    result = prepare_question_speech(
        "`https://example.com/files/a%2Fb`와 `https://example.com/files/a/b`의 "
        "차이를 설명해 주세요."
    )

    assert result.fragments == ()
    assert "파일스 에이 퍼센트 이 에프 비 경로와 파일스 에이 다음 구간 비 경로" in result.text
