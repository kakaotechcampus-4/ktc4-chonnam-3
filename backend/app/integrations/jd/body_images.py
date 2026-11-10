"""공고 본문의 텍스트와 이미지 참조만 읽으며 URL을 직접 요청하지 않는다."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.integrations.search.tavily import SearchError, checked_source_url

WANTED_IMAGE_DOMAINS = ("wanted.co.kr",)


class _Body(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        if tag == "img":
            values = dict(attrs)
            source = values.get("src") or values.get("data-src")
            if source:
                self.images.append(source)
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
        elif tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def body_text(value: str) -> tuple[str, list[str]]:
    if not re.search(r"<(?:img|p|div|br|ul|ol|li|span|strong|em)\b", value, re.I):
        return value, []
    parser = _Body()
    parser.feed(value)
    return "\n".join(
        line.strip() for line in "".join(parser.parts).splitlines() if line.strip()
    ), parser.images


def body_image_urls(
    detail: dict[str, object], html_images: list[str], base: str
) -> tuple[list[str], list[str]]:
    candidates: list[object] = list(html_images)
    limitations: list[str] = []
    # 회사 사진·로고가 섞인 job.images는 공고 본문 근거로 대신 사용하지 않는다.
    for key in ("image_urls", "images", "description_images"):
        value = detail.get(key)
        if value is not None:
            if isinstance(value, list):
                candidates.extend(value[:32])
                if len(value) > 32:
                    limitations.append("image_url_list_truncated")
            else:
                limitations.append("invalid_body_image_field")
    if detail.get("image_url") is not None:
        candidates.append(detail["image_url"])
    result: list[str] = []
    for raw in candidates[:32]:
        if isinstance(raw, dict):
            raw = raw.get("url") or raw.get("origin")
            if isinstance(raw, dict):
                raw = raw.get("url")
        try:
            if not isinstance(raw, str):
                raise SearchError("invalid_source")
            url = checked_source_url(urljoin(base, raw), WANTED_IMAGE_DOMAINS)
        except (SearchError, ValueError):
            limitations.append("untrusted_body_image_url")
            continue
        if url not in result:
            result.append(url)
    if len(candidates) > 32:
        limitations.append("image_url_list_truncated")
    return result, list(dict.fromkeys(limitations))
