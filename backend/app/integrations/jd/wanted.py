"""원티드 어댑터 — Sprint 1 유일. /wd/{id} → /api/chaos/jobs/v1/{id}/details 공개 JSON.

position / intro / main_tasks / requirements / preferred_points / benefits / skill_tags 가
항목별로 이미 나뉘어 오므로 요구사항 추출에 LLM 이 필요 없다. content_form='text'.

확정본 §3 3사 비교 / task-09
"""

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.integrations.jd.base import (
    FetchedPosting,
    JdFetchError,
    JdRequirementItem,
)
from app.shared.enums import RequirementType

_WD_PATH = re.compile(r"^/wd/(?P<id>\d+)")
_HOSTS = {"wanted.co.kr", "www.wanted.co.kr", "kr.wanted.co.kr"}
_BULLET = re.compile(r"^[\s\-•·*●■∙]+")
_DETAIL_API = "https://www.wanted.co.kr/api/chaos/jobs/v1/{posting_id}/details"

#: 구조화 필드 -> requirement_type. main_tasks/intro/benefits 는 요구사항이 아니라 제외한다.
_REQUIREMENT_FIELDS: tuple[tuple[str, RequirementType], ...] = (
    ("requirements", RequirementType.REQUIRED),
    ("preferred_points", RequirementType.PREFERRED),
    ("preferred", RequirementType.PREFERRED),
)


class WantedAdapter:
    """Wanted 공개 JSON 어댑터."""

    name = "wanted"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    # ── URL ──────────────────────────────────────────────────────────
    def matches(self, url: str) -> bool:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.netloc.lower() in _HOSTS and bool(_WD_PATH.match(parsed.path))

    def posting_id(self, url: str) -> str:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        matched = _WD_PATH.match(parsed.path)
        if not matched:
            raise JdFetchError(f"not a wanted posting url: {url}")
        return matched.group("id")

    def normalize(self, url: str) -> str:
        """query/fragment 를 버린 `https://www.wanted.co.kr/wd/{id}` 로 맞춘다."""
        return f"https://www.wanted.co.kr/wd/{self.posting_id(url)}"

    # ── fetch ────────────────────────────────────────────────────────
    async def fetch(self, url: str) -> FetchedPosting:
        posting_id = self.posting_id(url)
        api_url = _DETAIL_API.format(posting_id=posting_id)
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(api_url, headers={"Accept": "application/json"})
            if response.status_code >= 400:
                raise JdFetchError(f"wanted responded {response.status_code}")
            payload: dict[str, Any] = response.json()
        except JdFetchError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise JdFetchError(f"wanted fetch failed: {posting_id}") from exc
        finally:
            if self._client is None:
                await client.aclose()
        return self._to_posting(posting_id, api_url, payload)

    def _to_posting(self, posting_id: str, api_url: str, payload: dict[str, Any]) -> FetchedPosting:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(data, dict):
            raise JdFetchError("unexpected wanted payload")
        detail = _as_dict(data.get("detail") or data.get("job_detail"))
        company = _as_dict(data.get("company"))
        skill_tags = _skill_tags(data.get("skill_tags"))
        raw_text = "\n\n".join(
            f"[{key}]\n{value}"
            for key, value in detail.items()
            if isinstance(value, str) and value.strip()
        )
        if not raw_text.strip():
            raise JdFetchError("wanted posting has no text content")
        return FetchedPosting(
            site_adapter=self.name,
            fetch_url=api_url,
            normalized_url=f"https://www.wanted.co.kr/wd/{posting_id}",
            external_id=posting_id,
            position=_as_str(data.get("position")) or _as_str(data.get("name")),
            company_name=_as_str(company.get("name")) or _as_str(data.get("company_name")),
            raw_text=raw_text,
            raw_json=data,
            skill_tags=skill_tags,
            content_form="text",
        )

    # ── 결정적 추출 (LLM 없음) ───────────────────────────────────────
    def extract_requirements(self, posting: FetchedPosting) -> list[JdRequirementItem]:
        """requirements/preferred_points 를 줄 단위로 쪼개고 skill_tag 를 붙인다."""
        detail = _as_dict((posting.raw_json or {}).get("detail") or (posting.raw_json or {}))
        items: list[JdRequirementItem] = []
        seen: set[str] = set()
        for field_name, requirement_type in _REQUIREMENT_FIELDS:
            value = detail.get(field_name)
            if not isinstance(value, str):
                continue
            for line in _split_lines(value):
                key = f"{requirement_type}:{line}"
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    JdRequirementItem(
                        requirement_type=str(requirement_type),
                        text=line,
                        tech_tags=_matched_tags(line, posting.skill_tags),
                    )
                )
        return items


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _skill_tags(value: Any) -> list[str]:
    """`skill_tags` 는 [{title}] 또는 문자열 배열로 온다. tech_tags 원천."""
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
        elif isinstance(item, dict):
            title = _as_str(item.get("title")) or _as_str(item.get("name"))
            if title:
                tags.append(title)
    return list(dict.fromkeys(tags))


def _split_lines(text: str) -> list[str]:
    """줄바꿈과 불릿 기호로 자른다. 너무 짧은 줄(머리말)은 버린다."""
    lines: list[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = _BULLET.sub("", raw).strip()
        if len(line) < 2:
            continue
        lines.append(line)
    return lines


def _matched_tags(line: str, skill_tags: list[str]) -> list[str]:
    lowered = line.lower()
    return [tag for tag in skill_tags if tag.lower() in lowered]
