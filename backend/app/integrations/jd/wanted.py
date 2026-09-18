"""원티드 어댑터 — 1차 유일. /wd/{id} → /api/chaos/jobs/v1/{id}/details 공개 JSON
position / intro / main_tasks / requirements / preferred_points / benefits / skill_tags /
industry_name 이 항목별로 이미 나뉘어 옴. content_form='text'. 헤드리스 브라우저 불필요

확정본 §3 3사 비교 / task-09

주의: 아래 JSON 경로(`detail.job.*`)는 공개 문서가 없는 비공식 엔드포인트라 추정 기반으로 작성함
실제 공고 2건(job id 380611, 341487)으로 검증하며 position·skill_tags 경로 오류 발견해 수정함
`tests/contract/` 고정 픽스처로 대조하는 작업은 아직 안 함
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.integrations.jd.base import (
    PostingContent,
    PostingContentEmptyError,
    PostingUnreachableError,
    UnsupportedSiteError,
)

_WANTED_URL_RE = re.compile(r"wanted\.co\.kr/wd/(?P<job_id>\d+)")
_DETAIL_URL = "https://www.wanted.co.kr/api/chaos/jobs/v1/{job_id}/details"
_TIMEOUT_SECONDS = 10.0


def extract_job_id(url: str) -> str | None:
    """`https://www.wanted.co.kr/wd/12345` 형태에서 `12345`를 뽑음. 매칭 안 되면 None"""
    match = _WANTED_URL_RE.search(url)
    return match.group("job_id") if match else None


class WantedAdapter:
    site_adapter = "wanted"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self, url: str) -> PostingContent:
        job_id = extract_job_id(url)
        if job_id is None:
            # resolver 가 이미 걸러줘야 정상이지만, 방어적으로도 unsupported 로 취급
            raise UnsupportedSiteError(f"원티드 URL에서 job id를 못 찾음: {url}")

        detail_url = _DETAIL_URL.format(job_id=job_id)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
        try:
            try:
                response = await client.get(detail_url)
            except httpx.HTTPError as exc:
                raise PostingUnreachableError(str(exc)) from exc

            if response.status_code == 404:
                raise PostingUnreachableError(f"원티드 공고를 찾을 수 없음: {detail_url}")
            if response.status_code >= 400:
                raise PostingUnreachableError(
                    f"원티드 응답 실패: {response.status_code} {detail_url}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise PostingUnreachableError("원티드 응답이 JSON이 아님") from exc
        finally:
            if owns_client:
                await client.aclose()

        return self._parse(detail_url, payload)

    def _parse(self, fetch_url: str, payload: dict[str, Any]) -> PostingContent:
        job = payload.get("job") or payload.get("data", {}).get("job") or {}
        detail = job.get("detail") or {}
        company = job.get("company") or {}

        # 실제 응답(2026-09-14, job id 380611)엔 job.position/job.title 이 둘 다 없고
        # detail.position 에만 있었음 — 나머지 둘은 혹시 몰라 폴백으로 남겨둠
        position = detail.get("position") or job.get("position") or job.get("title")
        company_name = company.get("name")
        industry = company.get("industry_name")

        requirements = _split_paragraphs(detail.get("requirements"))
        preferred_points = _split_paragraphs(detail.get("preferred_points"))
        main_tasks = _split_paragraphs(detail.get("main_tasks"))
        intro = detail.get("intro") or ""

        # 실제 응답(job id 341487)엔 태그 이름이 "name"이 아니라 "text" 키에 있었음
        skill_tags = [
            tag.get("text") if isinstance(tag, dict) else str(tag)
            for tag in (job.get("skill_tags") or [])
            if tag
        ]

        raw_text_parts = [
            part
            for part in (
                position,
                intro,
                *main_tasks,
                *requirements,
                *preferred_points,
            )
            if part
        ]
        raw_text = "\n".join(raw_text_parts)

        if not raw_text and not requirements and not preferred_points and not main_tasks:
            raise PostingContentEmptyError(f"원티드 공고 본문이 비어있음: {fetch_url}")

        return PostingContent(
            site_adapter=self.site_adapter,
            fetch_url=fetch_url,
            content_form="text",
            raw_text=raw_text,
            position=position,
            company_name=company_name,
            industry=industry,
            requirements=requirements,
            preferred_points=preferred_points,
            main_tasks=main_tasks,
            skill_tags=[tag for tag in skill_tags if tag],
        )


def _split_paragraphs(value: object) -> list[str]:
    """원티드 필드는 리스트(항목별) 또는 개행 구분 단일 문자열로 올 수 있어 둘 다 받음"""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]
