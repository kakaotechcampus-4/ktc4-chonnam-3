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


def test_conflict_within_one_sentence_falls_back_to_etc():
    result = detect_domain_signal(_posting(main_tasks=["숙박 예약 서비스의 결제 연동 개발"]))

    # "결제"(finance)와 "숙박"(travel)이 같은 문장에 동시에 있어 충돌하므로 etc로 남는다.
    assert result.category == "etc"
    assert {m.keyword for m in result.matches} == {"결제", "숙박"}


def test_conflicting_category_signals_fall_back_to_etc_but_keep_matches():
    result = detect_domain_signal(
        _posting(
            main_tasks=["커머스 서비스의 결제 API 개발"], preferred_points=["게임 서버 운영 경험"]
        )
    )

    assert result.category == "etc"
    categories_found = {m.keyword for m in result.matches}
    assert "커머스" in categories_found or "결제" in categories_found
    assert "게임" in categories_found


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
