"""공고 원문과 도메인 판정 이력을 분리하며 모델 호출 동안 DB 트랜잭션을 열지 않는다."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.domain_category import DomainDecision
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.posting import JobPosting
from app.llm_tasks.domain_category import classify_posting_domain
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)

DOMAIN_METADATA_KEY = "_domain_classification"
DOMAIN_LAST_ATTEMPT_KEY = "_domain_classification_last_attempt"
DOMAIN_LAST_SUCCESS_KEY = "_domain_classification_last_success"


def _input(raw: dict[str, object]) -> c.DomainPostingInput:
    def text(key: str) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) and value.strip() else None

    def texts(key: str) -> tuple[str, ...]:
        value = raw.get(key)
        original = (
            tuple(item for item in value if isinstance(item, str) and item.strip())
            if isinstance(value, list)
            else ()
        )
        extraction = raw.get("_image_extraction")
        if not isinstance(extraction, dict) or extraction.get("status") not in {
            "succeeded",
            "partial",
        }:
            return original
        category = {
            "main_tasks": "responsibility",
            "requirements": "required",
            "preferred_points": "preferred",
        }.get(key)
        entries = extraction.get("requirements", [])
        extra = (
            tuple(
                item["text"]
                for item in entries
                if isinstance(item, dict)
                and item.get("category") == category
                and isinstance(item.get("text"), str)
            )
            if isinstance(entries, list)
            else ()
        )
        return tuple(dict.fromkeys((*original, *extra)))

    # 회사명·업종·공고 전체 raw_text를 직무의 도메인 근거로 대신 넣지 않는다.
    return c.DomainPostingInput(
        text("position"),
        text("intro"),
        texts("main_tasks"),
        texts("requirements"),
        texts("preferred_points"),
    )


def _digest(source: c.DomainPostingInput) -> str:
    return hashlib.sha256(
        json.dumps(asdict(source), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def classify_saved_posting(
    sessions: async_sessionmaker[AsyncSession],
    posting_id: UUID,
    *,
    settings: Settings,
    http_client: httpx.AsyncClient,
    force: bool = False,
) -> None:
    prompt: c.PromptSpec | None = None
    failure: c.CallFailure | None = None
    async with sessions() as db:
        posting = await db.get(JobPosting, posting_id)
        if (
            posting is None
            or posting.parse_status != "succeeded"
            or not isinstance(posting.raw_payload, dict)
        ):
            return
        raw = dict(posting.raw_payload)
        previous = raw.get(DOMAIN_METADATA_KEY)
        previous_attempt = raw.get(DOMAIN_LAST_ATTEMPT_KEY)
        # 별도 이력 없이 저장된 확정 분류는 수동/선행 결정일 수 있어 덮어쓰지 않는다.
        if posting.domain_category is not None and previous is None:
            return
        source = _input(raw)
        digest = _digest(source)
        try:
            prompt = await load_active_prompt(db, "domain_category")
        except (PromptNotFoundError, PromptConfigurationError):
            failure = c.CallFailure(
                "provider", "domain_category_prompt_unavailable", "Domain prompt unavailable."
            )
        version = prompt.version if prompt else None
        if (
            not force
            and isinstance(previous, dict)
            and previous.get("status") == "succeeded"
            and previous.get("input_hash") == digest
            and previous.get("prompt_version") == version
        ):
            return

    # 공급자 호출과 설정 검증은 읽기 트랜잭션을 닫은 뒤 수행한다.
    if failure is not None:
        decision = DomainDecision("etc", None, failure, ())
    else:
        try:
            llm = settings.require_llm()
        except ValueError:
            decision = DomainDecision(
                "etc",
                None,
                c.CallFailure(
                    "provider",
                    "domain_category_configuration_unavailable",
                    "Domain model configuration unavailable.",
                ),
                (),
            )
        else:
            assert prompt is not None
            decision = await classify_posting_domain(
                source, prompt=prompt, settings=llm, http_client=http_client
            )

    metadata = {
        "status": "failed" if decision.failure else "succeeded",
        "input_hash": digest,
        "prompt_version": version,
        "requested_model": prompt.model if prompt else None,
        "evidence": decision.evidence,
        "failure": asdict(decision.failure) if decision.failure else None,
        "attempts": [asdict(attempt) for attempt in decision.attempts],
        "classified_at": datetime.now(UTC).isoformat(),
    }
    async with sessions.begin() as db:
        current = await db.scalar(
            select(JobPosting).where(JobPosting.id == posting_id).with_for_update()
        )
        if current is None or not isinstance(current.raw_payload, dict):
            return
        if _digest(_input(current.raw_payload)) != digest:
            return
        if (
            current.raw_payload.get(DOMAIN_METADATA_KEY) != previous
            or current.raw_payload.get(DOMAIN_LAST_ATTEMPT_KEY) != previous_attempt
        ):
            # 늦은 이전 호출이 더 최근 판정이나 다른 원문의 분류를 덮어쓰지 않는다.
            return
        raw = {**current.raw_payload, DOMAIN_LAST_ATTEMPT_KEY: metadata}
        same_success = False
        if (
            isinstance(previous, dict)
            and previous.get("status") == "succeeded"
            and current.domain_category is not None
        ):
            raw[DOMAIN_LAST_SUCCESS_KEY] = {**previous, "category": current.domain_category}
            same_success = previous.get("input_hash") == digest
        if decision.failure and same_success:
            # 같은 원문의 마지막 성공과 이번 실패를 분리한다. 새 프롬프트 성공으로 위장하지 않는다.
            current.raw_payload = raw
            return
        # 원문이 바뀌면 과거 성공은 이력일 뿐 현재 공고의 분류로 재사용하지 않는다.
        current.domain_category = None if decision.failure else decision.category
        raw[DOMAIN_METADATA_KEY] = metadata
        if decision.failure is None:
            raw[DOMAIN_LAST_SUCCESS_KEY] = {**metadata, "category": decision.category}
        current.raw_payload = raw
