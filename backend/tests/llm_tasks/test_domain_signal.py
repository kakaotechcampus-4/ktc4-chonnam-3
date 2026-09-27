from app.integrations.jd.base import PostingContent
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

    # main_tasks(2) > preferred_points(1)
    assert result.category == "shopping"
    assert {m.keyword for m in result.matches} == {"커머스"}


def test_tied_top_score_falls_back_to_etc_but_keeps_matches():
    result = detect_domain_signal(
        _posting(requirements=["금융 서비스 개발 경험"], preferred_points=["게임 서버 운영 경험"])
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
