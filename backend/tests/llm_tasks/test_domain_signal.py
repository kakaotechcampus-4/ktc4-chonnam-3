import pytest

from app.integrations.jd.base import PostingContent
from app.integrations.jd.wanted import WantedAdapter
from app.llm_tasks.domain_signal import detect_domain_signal


def _posting(**overrides) -> PostingContent:
    defaults = dict(
        site_adapter="wanted",
        fetch_url="https://www.wanted.co.kr/wd/1",
        content_form="text",
    )
    defaults.update(overrides)
    return PostingContent(**defaults)


def test_company_name_is_never_used_as_a_signal():
    """W5 완료 기준: 회사명만으로 도메인을 강제 분류하지 않음."""
    result = detect_domain_signal(
        _posting(
            company_name="ABC파이낸스",
            position="백엔드 개발자",
            main_tasks=["내부 어드민 도구 개발"],
        )
    )

    assert result.category == "etc"
    assert result.matches == ()


def test_no_signal_anywhere_falls_back_to_etc():
    result = detect_domain_signal(
        _posting(position="백엔드 개발자", main_tasks=["내부 어드민 도구 개발"])
    )

    assert result.category == "etc"
    assert result.matches == ()


def test_single_text_signal_is_adopted():
    result = detect_domain_signal(_posting(main_tasks=["여행 상품 예약 시스템 개발"]))

    assert result.category == "travel"
    assert len(result.matches) == 1
    assert result.matches[0].source_field == "main_tasks"
    assert result.matches[0].keyword == "여행"


def test_generic_feature_words_do_not_create_a_conflict():
    """결제·예약은 여러 도메인에 공통인 기능 단어라 키워드가 아니다 (0021)."""
    result = detect_domain_signal(_posting(main_tasks=["숙박 예약 서비스의 결제 연동 개발"]))

    assert result.category == "travel"
    assert {m.keyword for m in result.matches} == {"숙박"}


def test_stronger_field_wins_over_weaker_conflicting_signal():
    result = detect_domain_signal(
        _posting(main_tasks=["커머스 서비스의 API 개발"], preferred_points=["게임 서버 운영 경험"])
    )

    # main_tasks(3) > preferred_points(1)
    assert result.category == "shopping"
    assert {m.keyword for m in result.matches} == {"커머스"}


def test_requirements_outweigh_preferred_points():
    """우대사항을 필수 요건처럼 다루지 않는다 (W5 완료 기준)."""
    result = detect_domain_signal(
        _posting(requirements=["금융 서비스 개발 경험"], preferred_points=["게임 서버 운영 경험"])
    )

    assert result.category == "finance"


def test_tied_top_score_falls_back_to_etc_but_keeps_matches():
    result = detect_domain_signal(
        _posting(requirements=["금융 서비스 개발 경험", "게임 서버 운영 경험"])
    )

    assert result.category == "etc"
    assert {m.keyword for m in result.matches} == {"금융", "게임"}


def test_company_industry_is_never_used_as_a_signal():
    """원티드 industry_name은 회사 단위 값이라 company_name과 같은 이유로 무시한다 (0021)."""
    result = detect_domain_signal(
        _posting(industry="게임", position="백엔드 개발자", main_tasks=["내부 어드민 도구 개발"])
    )

    assert result.category == "etc"
    assert result.matches == ()


def test_matched_text_preserves_the_original_source_sentence():
    result = detect_domain_signal(_posting(requirements=["의료 데이터를 다루는 서비스 개발 경험"]))

    assert result.category == "medical"
    assert result.matches[0].matched_text == "의료 데이터를 다루는 서비스 개발 경험"
    assert result.matches[0].source_field == "requirements"


@pytest.mark.parametrize(
    "posting",
    [
        {"main_tasks": ["기술적 제약을 고려한 API 설계 및 개발"]},
        {"requirements": ["데이터베이스 제약 조건과 트랜잭션에 대한 이해"]},
        {"main_tasks": ["슬라이더와 캐러셀 UI 컴포넌트 개발"]},
        # 실제 원티드 공고 문장 (2026-10-05 개발 공고 600건 확인)
        {"requirements": ["다양한 직무와 모델 제약사항, QA 항목을 커뮤니케이션할 수 있으신 분"]},
        {"main_tasks": ["보상함수와 제약 정의를 주도합니다"]},
        {"requirements": ["사내정치, 프리라이더는 생존할 수 없습니다."]},
    ],
)
def test_general_tech_terms_are_not_domain_signals(posting):
    """일반적인 "제약"(제한)과 "슬라이더" 속 "라이더"는 의료·모빌리티 근거가 아니다."""
    result = detect_domain_signal(_posting(**posting))

    assert result.category == "etc"
    assert result.matches == ()


@pytest.mark.parametrize(
    ("text", "category", "keyword"),
    [
        ("제약사 영업 지원 시스템 개발", "medical", "제약사"),
        ("의약품 유통 데이터 파이프라인 개발", "medical", "의약품"),
        ("라이더 앱 개발", "mobility", "라이더"),
        ("배달 라이더 정산 시스템 개발", "mobility", "라이더"),
        # 실제 원티드 공고 문장
        ("전 세계 제약사·바이오텍의 BD 조직을 지원하는 플랫폼 개발", "medical", "제약사"),
    ],
)
def test_real_pharma_and_rider_services_are_still_detected(text, category, keyword):
    result = detect_domain_signal(_posting(main_tasks=[text]))

    assert result.category == category
    assert keyword in {m.keyword for m in result.matches}


@pytest.mark.parametrize("text", ["mmorpg 서버 개발", "E스포츠 대회 플랫폼 개발"])
def test_english_keywords_ignore_case_but_keep_original_text(text):
    result = detect_domain_signal(_posting(main_tasks=[text]))

    assert result.category == "game"
    assert result.matches[0].matched_text == text


def test_same_wanted_content_gives_same_result_regardless_of_input_shape():
    """원티드가 같은 내용을 문자열로 주든, 여러 줄 문자열 하나를 담은 목록으로 주든 결과가 같다."""
    lines = ["금융 서비스 개발 경험", "금융 서비스 운영 경험", "금융 규제 이해"]
    text = "\n".join(lines)

    def detect(requirements):
        payload = {
            "job": {"detail": {"position": "커머스 백엔드 개발자", "requirements": requirements}}
        }
        return detect_domain_signal(
            WantedAdapter()._parse("https://www.wanted.co.kr/wd/1", payload)
        )

    as_string, as_list = detect(text), detect([text])

    assert as_string == as_list
    # requirements 금융 3건(2×3=6) > position 커머스(4)
    assert as_string.category == "finance"
    assert [m.matched_text for m in as_string.matches] == lines
