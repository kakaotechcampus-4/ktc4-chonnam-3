"""Elice Helpy Document Vision의 문서 제출·유한 폴링 어댑터.

공식 모델 페이지의 multipart 예시를 따른다. 표의 /jobs와 실행 예시 /v1/jobs가
다르므로 상태 경로는 명시 설정으로 유지한다. 원문 content와 생성 description을 섞지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr


class VisionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class EliceVisionSettings:
    base_url: str
    api_key: SecretStr
    model: str = "eliceai/helpy-document-vision"
    timeout_seconds: float = 60
    max_file_bytes: int = 20971520
    max_response_bytes: int = 8388608
    max_polls: int = 12
    poll_interval_seconds: float = 1
    job_path_template: str = "/v1/jobs/{job_id}"

    def __post_init__(self) -> None:
        invalid = "Invalid vision base URL"
        try:
            parsed = urlsplit(self.base_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or "\\" in self.base_url
                or any(c.isspace() for c in self.base_url)
            ):
                raise ValueError(invalid)
            _ = parsed.port
        except ValueError:
            raise ValueError(invalid) from None
        # 콘솔의 API base(/v1)와 서비스 root를 모두 받아 버전 경로를 한 번만 붙인다.
        base = self.base_url.rstrip("/")
        object.__setattr__(self, "base_url", base[:-3] if base.endswith("/v1") else base)
        if not self.api_key.get_secret_value().strip() or not self.model.strip():
            raise ValueError("Vision credentials and model are required")
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or not math.isfinite(self.poll_interval_seconds)
            or self.poll_interval_seconds < 0
        ):
            raise ValueError("Invalid vision time limits")
        if any(
            type(x) is not int or x <= 0
            for x in (self.max_file_bytes, self.max_response_bytes, self.max_polls)
        ):
            raise ValueError("Invalid vision limits")
        if self.job_path_template not in ("/v1/jobs/{job_id}", "/jobs/{job_id}"):
            raise ValueError("Unsupported vision job path")


@dataclass(frozen=True)
class VisionBlock:
    page: int
    element_index: int
    label: str
    content: str | None
    description: str | None
    coordinate: object | None


@dataclass(frozen=True)
class VisionResult:
    job_id: str
    blocks: tuple[VisionBlock, ...]
    page_count: int
    raw_result: dict[str, object]
    limitations: tuple[str, ...] = ()


_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class EliceVisionClient:
    def __init__(
        self, settings: EliceVisionSettings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings, self.transport = settings, transport

    async def extract(
        self, data: bytes, mime_type: str, *, filename: str = "document"
    ) -> VisionResult:
        if mime_type not in _MIMES:
            raise VisionError("unsupported_document")
        if not data:
            raise VisionError("empty_document")
        if len(data) > self.settings.max_file_bytes:
            raise VisionError("document_too_large")
        # 원본 파일명은 모델 호출·로그에 필요하지 않으므로 경로와 제어 문자를 제거한다.
        safe_name = (
            re.sub(r"[^A-Za-z0-9._-]", "_", filename.replace("\\", "/").rsplit("/", 1)[-1])[:128]
            or "document"
        )
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                    headers={"Authorization": "Bearer " + self.settings.api_key.get_secret_value()},
                ) as client:
                    submitted = await self._request(
                        client,
                        "POST",
                        "/v1/documents",
                        data={
                            "model": self.settings.model,
                            "configs": json.dumps(
                                {"do_image_description": True, "do_chart_conversion": True}
                            ),
                        },
                        files={"document": (safe_name, data, mime_type)},
                    )
                    job_id = submitted.get("job_id")
                    if not isinstance(job_id, str) or not re.fullmatch(
                        r"[A-Za-z0-9_-]{1,128}", job_id
                    ):
                        raise VisionError("invalid_response")
                    for attempt in range(self.settings.max_polls):
                        if attempt:
                            await asyncio.sleep(self.settings.poll_interval_seconds)
                        status = await self._request(
                            client, "GET", self.settings.job_path_template.format(job_id=job_id)
                        )
                        state = status.get("status")
                        if state == "succeeded":
                            return self._result(job_id, status.get("result"))
                        if state in ("failure", "failed", "cancelled"):
                            raise VisionError("extraction_failed")
                        if not isinstance(state, str) or not state:
                            raise VisionError("invalid_response")
                    raise VisionError("poll_limit")
        except (httpx.TimeoutException, TimeoutError):
            raise VisionError("timeout") from None
        except httpx.HTTPError:
            raise VisionError("provider_error") from None

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, object]:
        async with client.stream(
            method, self.settings.base_url.rstrip("/") + path, data=data, files=files
        ) as response:
            if response.status_code not in (200, 201, 202):
                code = response.status_code
                raise VisionError(
                    "unauthorized"
                    if code in (401, 403)
                    else "rate_limited"
                    if code == 429
                    else "provider_error"
                )
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > self.settings.max_response_bytes:
                    raise VisionError("response_too_large")
        try:
            value = json.loads(content)
        except (ValueError, UnicodeError):
            raise VisionError("invalid_response") from None
        if not isinstance(value, dict):
            raise VisionError("invalid_response")
        return value

    def _result(self, job_id: str, raw: object) -> VisionResult:
        if not isinstance(raw, dict) or not isinstance(raw.get("pages"), list) or not raw["pages"]:
            raise VisionError("invalid_response")
        blocks = []
        limitations = []
        for page_no, page in enumerate(raw["pages"], 1):
            if not isinstance(page, dict) or not isinstance(page.get("elements"), list):
                raise VisionError("invalid_response")
            for index, element in enumerate(page["elements"]):
                if not isinstance(element, dict) or not isinstance(element.get("label"), str):
                    raise VisionError("invalid_response")
                content, description = element.get("content"), element.get("description")
                if (
                    content is not None
                    and not isinstance(content, str)
                    or description is not None
                    and not isinstance(description, str)
                ):
                    raise VisionError("invalid_response")
                if content is None and description is None:
                    limitations.append("element_without_text")
                coordinate = element.get("coordinate")
                if coordinate is None:
                    # 실제 Document Vision 응답은 같은 위치를 bounding_box로 제공하기도 한다.
                    coordinate = element.get("bounding_box")
                blocks.append(
                    VisionBlock(
                        page_no,
                        index,
                        element["label"],
                        content,
                        description,
                        coordinate,
                    )
                )
        if not blocks:
            raise VisionError("empty_document")
        count = raw.get("page_count", len(raw["pages"]))
        if type(count) is not int or count < len(raw["pages"]):
            raise VisionError("invalid_response")
        if count != len(raw["pages"]):
            limitations.append("incomplete_pages")
        return VisionResult(job_id, tuple(blocks), count, raw, tuple(dict.fromkeys(limitations)))
