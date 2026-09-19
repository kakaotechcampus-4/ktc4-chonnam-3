"""원티드 어댑터 — 1차 유일. /wd/{id} → /api/chaos/jobs/v1/{id}/details 공개 JSON
position / intro / main_tasks / requirements / preferred_points / benefits / skill_tags /
industry_name 이 항목별로 이미 나뉘어 옴. content_form='text'. 헤드리스 브라우저 불필요
채용 마감 여부(status/due_time)는 분석 차단 조건이 아니다. 본문 수집·검증 결과로 판단한다.

확정본 §3 3사 비교 / task-09

주의: 아래 JSON 경로(`job.detail.*`)는 공개 문서가 없는 비공식 엔드포인트라 실제 응답으로 확인함
실제 공고 2건(job id 380611, 341487)으로 검증하며 position·skill_tags 경로 오류 발견해 수정함
`tests/contract/` 고정 픽스처로 대조하는 작업은 아직 안 함
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.integrations.jd.base import (
    PostingContent,
    PostingContentEmptyError,
    PostingInvalidResponseError,
    PostingUnreachableError,
    UnsupportedSiteError,
)

WANTED_HOSTS = {"www.wanted.co.kr", "wanted.co.kr"}
_WANTED_PATH_RE = re.compile(r"/wd/(?P<job_id>[0-9]+)/?")
_DETAIL_URL = "https://www.wanted.co.kr/api/chaos/jobs/v1/{job_id}/details"
_TIMEOUT_SECONDS = 10.0


def extract_job_id(url: str) -> str | None:
    """`https://www.wanted.co.kr/wd/12345` 형태에서 `12345`를 뽑음. 매칭 안 되면 None"""
    try:
        # 세미콜론 뒤의 잘못된 경로도 검사하도록 경로 전체를 보존한다.
        parsed = urlsplit(url)
        # 포트 접근 시 비숫자·범위 밖 포트도 ValueError로 검증된다.
        _ = parsed.port
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in WANTED_HOSTS:
            return None
    except ValueError:
        return None
    # 쿼리에 들어 있는 다른 공고 주소를 ID로 읽지 않고, 실제 경로만 검사한다.
    match = _WANTED_PATH_RE.fullmatch(parsed.path)
    return match.group("job_id") if match else None


class WantedAdapter:
    site_adapter = "wanted"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self, url: str) -> PostingContent:
        job_id = extract_job_id(url)
        if job_id is None:
            # resolver는 호스트를 선택하고, 어댑터는 공고 경로까지 검증한다.
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
            # 외부에서 주입한 클라이언트는 호출부가 재사용할 수 있으므로 닫지 않는다.
            if owns_client:
                await client.aclose()

        return self._parse(detail_url, payload)

    def _parse(self, fetch_url: str, payload: object) -> PostingContent:
        if not isinstance(payload, dict):
            raise PostingInvalidResponseError("원티드 응답이 JSON 객체가 아님")
        job = _object_field(payload.get("job"))
        if not job:
            # 응답이 data로 감싸진 형식도 동일한 객체 검증을 거쳐 읽는다.
            job = _object_field(_object_field(payload.get("data")).get("job"))
        detail = _object_field(job.get("detail"))
        company = _object_field(job.get("company"))

        # 실제 응답(2026-09-14, job id 380611)엔 job.position/job.title 이 둘 다 없고
        # detail.position 에만 있었음 — 나머지 둘은 혹시 몰라 폴백으로 남겨둠
        position = (
            _optional_text(detail.get("position"))
            or _optional_text(job.get("position"))
            or _optional_text(job.get("title"))
        )
        company_name = _optional_text(company.get("name"))
        industry = _optional_text(company.get("industry_name"))

        requirements = _split_paragraphs(detail.get("requirements"))
        preferred_points = _split_paragraphs(detail.get("preferred_points"))
        main_tasks = _split_paragraphs(detail.get("main_tasks"))
        intro = _optional_text(detail.get("intro"))

        # 실제 응답(job id 341487)엔 태그 이름이 "name"이 아니라 "text" 키에 있었음
        tag_values = job.get("skill_tags")
        if tag_values is None:
            tag_values = []
        if not isinstance(tag_values, list):
            raise PostingInvalidResponseError("원티드 skill_tags가 목록이 아님")
        skill_tags = []
        for tag in tag_values:
            text = tag.get("text") if isinstance(tag, dict) else tag
            if not isinstance(text, str):
                raise PostingInvalidResponseError("원티드 기술 태그의 text가 문자열이 아님")
            if text.strip():
                skill_tags.append(text.strip())

        raw_text_parts = [
            part
            for part in (
                position,
                intro,
                *main_tasks,
                *requirements,
                *preferred_points,
            )
            if part and part.strip()
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
            skill_tags=skill_tags,
        )


def _object_field(value: object) -> dict[str, Any]:
    """누락·null인 선택 객체는 허용하되 목록·숫자 등 잘못된 타입은 거부한다."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PostingInvalidResponseError("원티드 응답의 객체 필드 형식이 올바르지 않음")
    return value


def _optional_text(value: object) -> str | None:
    """숫자나 객체를 문자열로 바꿔 실제 공고 내용처럼 저장하지 않는다."""
    if value is not None and not isinstance(value, str):
        raise PostingInvalidResponseError("원티드 응답의 텍스트 필드가 문자열이 아님")
    return value


def _split_paragraphs(value: object) -> list[str]:
    """원티드 필드는 리스트(항목별) 또는 개행 구분 단일 문자열로 올 수 있어 둘 다 받음"""
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    # 잘못된 항목을 조용히 버리면 누락된 요구사항을 정상 추출로 오인할 수 있다.
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PostingInvalidResponseError("원티드 본문 필드가 문자열 또는 문자열 목록이 아님")
    return [item.strip() for item in value if item.strip()]
