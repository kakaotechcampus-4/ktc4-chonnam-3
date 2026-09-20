"""원티드 어댑터 — 1차 유일. /wd/{id} → /api/chaos/jobs/v1/{id}/details 공개 JSON.
position / intro / main_tasks / requirements / preferred_points / benefits / skill_tags /
industry_name 이 항목별로 이미 나뉘어 온다. content_form='text'. 헤드리스 브라우저 불필요.

확정본 §3 3사 비교 / task-09

실제 응답으로 확인한 구조 (2026-09-21):

    {"application": null,
     "job": {"id": 123456, "status": "close",
             "detail": {"position", "intro", "main_tasks", "requirements",
                        "preferred_points", "benefits", "hire_rounds"},
             "company": {"id", "name", "industry_name", "company_tags"},
             "skill_tags": [{"tag_type_id": 1411, "text": "Git"}],
             "category_tag": {"parent_tag": {"text"}, "child_tags": [{"text"}]}}}

  data 래퍼가 없고 position 은 job.detail 안에 있다. 없는 공고는 404 +
  {"error_code": 11001, "message": "job not found exception"} 이다.
  키 이름으로 깊이 탐색하는 방식은 유지한다 — 문서화되지 않은 외부 API 라
  경로를 고정하면 구조가 조금만 바뀌어도 전부 실패한다.
"""

import re
from typing import Any

import httpx

from app.integrations.jd.base import (
    JD_ERROR_EXTRACTION_FAILED,
    JD_ERROR_FETCH_FAILED,
    JD_ERROR_NOT_A_JOB_POSTING,
    ContentForm,
    JdFetchResult,
    JdParseStatus,
    JdRequirementItem,
    JobPostingPayload,
    failure,
)
from app.shared.enums import JdCategory

WANTED_HOSTS = frozenset({"wanted.co.kr", "www.wanted.co.kr"})
_POSTING_ID = re.compile(r"/wd/(?P<posting_id>\d+)")
_DETAILS_URL = "https://www.wanted.co.kr/api/chaos/jobs/v1/{posting_id}/details"
_CANONICAL_URL = "https://www.wanted.co.kr/wd/{posting_id}"

# 줄머리 글머리표. 원티드 본문은 줄바꿈으로 항목이 나뉜다.
_BULLET = re.compile(r"^\s*(?:[-•·*–—]|\d+[.)])\s*")

# 확정본이 적어둔 항목 이름 -> 계약 category.
# 자격요건=required, 우대사항=preferred, 주요업무=responsibility 로 openapi JdCategory 와 맞는다.
_FIELD_CATEGORY: tuple[tuple[str, JdCategory], ...] = (
    ("main_tasks", JdCategory.RESPONSIBILITY),
    ("requirements", JdCategory.REQUIRED),
    ("preferred_points", JdCategory.PREFERRED),
)

DEFAULT_REQUIREMENT_LIMIT = 20
DEFAULT_TIMEOUT_SECONDS = 10.0


def _find_value(payload: object, key: str) -> Any:
    """중첩 dict/list 에서 key 를 처음 만나는 값으로 돌려준다.

    입력: 파싱된 JSON, 찾을 키. 출력: 값, 없으면 None.
    구조는 모듈 docstring 에 적어뒀지만 경로를 고정하지 않는다 — 문서화되지 않은
    외부 API 라 중첩이 조금만 바뀌어도 전부 실패하는 편보다 낫다.
    """
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = _find_value(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_value(item, key)
            if found is not None:
                return found
    return None


def _as_text(value: object) -> str | None:
    """문자열 필드를 정리한다. 입력: 임의 값. 출력: 비어 있지 않은 문자열 또는 None."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _split_lines(value: object) -> list[str]:
    """여러 줄 본문을 항목 목록으로 자른다. 입력: 본문. 출력: 글머리표를 뗀 줄 목록."""
    text = _as_text(value)
    if text is None:
        return []
    lines = []
    for raw_line in text.splitlines():
        line = _BULLET.sub("", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _skill_tags(payload: object) -> list[str]:
    """skill_tags 를 문자열 목록으로 만든다. dict 목록과 문자열 목록을 모두 받는다."""
    raw = _find_value(payload, "skill_tags")
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for item in raw:
        if isinstance(item, str):
            tag = _as_text(item)
        elif isinstance(item, dict):
            # 실제 응답은 {"tag_type_id": 1411, "text": "Git"} 이다.
            # title/name 은 attraction_tags·company_tags 쪽 형태라 폴백으로만 둔다.
            tag = (
                _as_text(item.get("text"))
                or _as_text(item.get("title"))
                or _as_text(item.get("name"))
            )
        else:
            tag = None
        if tag is not None and tag not in tags:
            tags.append(tag)
    return tags


def _requirements(payload: object, limit: int) -> list[JdRequirementItem]:
    """항목별 본문을 jd_requirements 목록으로 만든다.

    입력: 파싱된 JSON, 최대 개수. 출력: display_order 가 1부터 매겨진 목록.
    순서는 주요업무 -> 자격요건 -> 우대사항으로, 공고를 위에서 읽는 순서와 같다.
    """
    items: list[JdRequirementItem] = []
    for field_name, category in _FIELD_CATEGORY:
        for line in _split_lines(_find_value(payload, field_name)):
            if len(items) >= limit:
                return items
            items.append(
                JdRequirementItem(category=category, text=line, display_order=len(items) + 1)
            )
    return items


def _company_name(payload: object) -> str | None:
    """회사명을 찾는다. company.name 과 company_name 양쪽을 본다."""
    company = _find_value(payload, "company")
    if isinstance(company, dict):
        name = _as_text(company.get("name"))
        if name is not None:
            return name
    return _as_text(_find_value(payload, "company_name"))


class WantedAdapter:
    """원티드 공개 JSON 어댑터. Sprint 1 은 이 어댑터 하나만 쓴다."""

    name = "wanted"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        requirement_limit: int = DEFAULT_REQUIREMENT_LIMIT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """입력: 주입할 httpx client(테스트용), 요구사항 상한, timeout. 출력: 없음."""
        self._client = client
        self._requirement_limit = requirement_limit
        self._timeout_seconds = timeout_seconds

    def supports(self, url: str) -> bool:
        """원티드 공고 URL 인지. 입력: 원본 URL. 출력: bool."""
        return self._posting_id(url) is not None

    def normalize_url(self, url: str) -> str | None:
        """https://www.wanted.co.kr/wd/{id} 로 정규화한다.

        입력: 원본 URL. 출력: 정규 URL, 원티드 공고가 아니면 None.
        job_postings 재사용 판정 키라서 query·hash·slash 차이를 모두 없앤다.
        """
        posting_id = self._posting_id(url)
        if posting_id is None:
            return None
        return _CANONICAL_URL.format(posting_id=posting_id)

    async def fetch(self, url: str) -> JdFetchResult:
        """공고를 가져와 구조화한다. 입력: 원본 URL. 출력: JdFetchResult."""
        posting_id = self._posting_id(url)
        if posting_id is None:
            return failure(self.name, JD_ERROR_NOT_A_JOB_POSTING)

        fetch_url = _DETAILS_URL.format(posting_id=posting_id)
        try:
            response = await self._get(fetch_url)
        except httpx.HTTPError:
            # timeout 과 연결 실패.
            return failure(self.name, JD_ERROR_FETCH_FAILED)

        if response.status_code == httpx.codes.NOT_FOUND:
            # {"error_code": 11001, "message": "job not found exception"} — 삭제된 공고다.
            return failure(self.name, JD_ERROR_NOT_A_JOB_POSTING)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            return failure(self.name, JD_ERROR_FETCH_FAILED)

        try:
            raw = response.json()
        except ValueError:
            return failure(self.name, JD_ERROR_FETCH_FAILED)

        if not isinstance(raw, dict):
            return failure(self.name, JD_ERROR_EXTRACTION_FAILED)

        position = _as_text(_find_value(raw, "position"))
        company_name = _company_name(raw)
        if position is None and company_name is None:
            # 공고 JSON 이 아니거나 삭제된 공고다.
            return failure(self.name, JD_ERROR_NOT_A_JOB_POSTING)

        requirements = _requirements(raw, self._requirement_limit)
        payload = JobPostingPayload(
            source=self.name,
            normalized_url=_CANONICAL_URL.format(posting_id=posting_id),
            raw_url=url,
            fetch_url=fetch_url,
            source_posting_id=posting_id,
            position=position,
            company_name=company_name,
            skill_tags=_skill_tags(raw),
            requirements=requirements,
            content_form=ContentForm.TEXT,
            raw_payload=raw,
        )
        # 공고는 받았지만 요구사항이나 직무명이 비면 부분 성공이다.
        complete = position is not None and bool(requirements)
        return JdFetchResult(
            adapter=self.name,
            status=JdParseStatus.SUCCEEDED if complete else JdParseStatus.PARTIAL,
            payload=payload,
        )

    async def _get(self, fetch_url: str) -> httpx.Response:
        """details 응답을 가져온다. 입력: API URL. 출력: Response.

        상태코드는 호출부가 본다 — 404 와 나머지 오류의 error_code 가 다르다.
        """
        if self._client is not None:
            return await self._client.get(fetch_url)
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.get(fetch_url)

    @staticmethod
    def _posting_id(url: str) -> str | None:
        """URL 에서 공고 번호를 뽑는다. 호스트가 원티드가 아니면 None."""
        try:
            parsed = httpx.URL(url if "://" in url else f"https://{url}")
        except (httpx.InvalidURL, ValueError, TypeError):
            return None
        if parsed.host.lower() not in WANTED_HOSTS:
            return None
        match = _POSTING_ID.search(parsed.path)
        return match.group("posting_id") if match else None
