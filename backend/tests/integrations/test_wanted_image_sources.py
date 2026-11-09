"""같은 Wanted URL의 본문 이미지만 보존하고 사내망·회사 갤러리는 판독하지 않는다."""

from app.integrations.jd.wanted import WantedAdapter


def test_image_only_posting_keeps_verified_body_image_urls():
    content = WantedAdapter()._parse(
        "https://www.wanted.co.kr/api/details",
        {
            "job": {
                "detail": {
                    "position": "개발자",
                    "image_urls": ["https://static.wanted.co.kr/jobs/jd.png"],
                }
            }
        },
    )
    assert content.content_form == "image"
    assert content.image_urls == ["https://static.wanted.co.kr/jobs/jd.png"]


def test_mixed_html_preserves_category_text_and_extracts_body_image():
    content = WantedAdapter()._parse(
        "https://www.wanted.co.kr/api/details",
        {
            "job": {
                "detail": {
                    "requirements": '<p>Python 경험</p><img src="//static.wanted.co.kr/jd.png">',
                    "preferred_points": ["Redis 경험"],
                },
                "images": [{"url": "https://static.wanted.co.kr/company/gallery.png"}],
            }
        },
    )
    assert content.content_form == "mixed"
    assert content.requirements == ["Python 경험"]
    assert content.preferred_points == ["Redis 경험"]
    assert content.image_urls == ["https://static.wanted.co.kr/jd.png"]


def test_untrusted_body_image_is_not_forwarded_to_vision():
    content = WantedAdapter()._parse(
        "https://www.wanted.co.kr/api/details",
        {
            "job": {
                "detail": {
                    "requirements": ["Python 경험"],
                    "image_urls": [
                        "https://127.0.0.1/internal",
                        "https://static.wanted.co.kr.evil.example/jd.png",
                    ],
                }
            }
        },
    )
    assert content.image_urls == []
    assert content.source_limitations
