"""이미지 전사·요구사항 검증을 연결한다. 모델 호출 중 DB transaction은 유지하지 않는다."""

from dataclasses import asdict, dataclass, replace

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.integrations.jd.base import PostingContent
from app.integrations.jd.images import collect_posting_images
from app.llm_tasks.jd_extract import MAX_REQUIREMENTS, JdRequirementDraft
from app.llm_tasks.jd_extract_image import analyze_image_requirements
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)


@dataclass(frozen=True)
class ImageDrafts:
    content: PostingContent
    drafts: list[JdRequirementDraft]
    source_refs: list[list[dict[str, object]]]


async def extend_image_drafts(
    sessions: async_sessionmaker[AsyncSession],
    content: PostingContent,
    drafts: list[JdRequirementDraft],
    *,
    settings: Settings | None,
    http_client: httpx.AsyncClient | None,
) -> ImageDrafts:
    refs: list[list[dict[str, object]]] = [[] for _ in drafts]
    metadata: dict[str, object] = {
        "version": "image-jd.v1",
        "status": "failed",
        "requirements": [],
        "attempts": [],
    }
    if settings is None:
        content = replace(
            content,
            source_limitations=[*content.source_limitations, "jd_image_settings_unavailable"],
        )
    else:
        content = await collect_posting_images(content, settings=settings, http_client=http_client)
    limitations = list(content.source_limitations)
    remaining = MAX_REQUIREMENTS - len(drafts)
    result = None
    if not content.source_blocks:
        limitations.append("image_transcription_unavailable")
    elif remaining <= 0:
        metadata["status"] = "succeeded"
        limitations.append("jd_requirement_limit")
    elif settings is not None:
        try:
            async with sessions() as db:
                prompt = await load_active_prompt(db, "jd_extract_image")
            llm = settings.require_llm()
        except (PromptNotFoundError, PromptConfigurationError, ValueError):
            limitations.append("jd_image_model_not_configured")
        else:
            # 전사 전체를 원문 snapshot에 남기고 모델에는 입력 예산 안의 완성된 줄만 보낸다.
            byte_limit = llm.llm_max_input_bytes // 2
            blocks: dict[str, str] = {}
            for block in content.source_blocks:
                text, identifier = str(block["text"]), str(block["block_id"])
                raw = text.encode()
                if len(raw) > byte_limit:
                    prefix = raw[:byte_limit].decode("utf-8", errors="ignore")
                    text = prefix[: prefix.rfind("\n") + 1] if "\n" in prefix else ""
                    limitations.append("image_jd_input_excerpt")
                if text.strip():
                    blocks[identifier] = text
                    byte_limit -= len(text.encode())
            if blocks:
                result = await analyze_image_requirements(
                    blocks,
                    prompt=prompt,
                    settings=llm,
                    http_client=http_client,
                    max_requirements=remaining,
                )
                metadata.update(
                    prompt_version=prompt.version,
                    requested_model=prompt.model,
                    attempts=[asdict(item) for item in result.attempts],
                    failure=asdict(result.failure) if result.failure else None,
                )
            else:
                limitations.append("image_jd_input_unavailable")
    if result is not None and result.data is not None:
        checked = result.data
        metadata.update(
            status="partial" if checked.rejected else "succeeded",
            requirements=[asdict(item) for item in checked.requirements],
            rejected=list(checked.rejected),
        )
        limitations.extend(checked.limitations)
        limitations.extend(checked.rejected)
        by_id = {str(block["block_id"]): block for block in content.source_blocks}
        merged = list(drafts)
        seen = {(item.category, item.text) for item in drafts}
        tags = list(content.skill_tags)
        accepted = []
        conflicts = []
        for item in checked.requirements:
            if any(draft.text == item.text and draft.category != item.category for draft in drafts):
                # 구조화 필드와 이미지의 분류가 다르면 기존 분류를 바꾸지 않고 차이를 남긴다.
                conflicts.append(asdict(item))
                limitations.append("image_structured_category_conflict")
                continue
            accepted.append(asdict(item))
            if (item.category, item.text) in seen:
                continue
            seen.add((item.category, item.text))
            merged.append(
                JdRequirementDraft(item.category, item.text, len(merged), list(item.tech_tags))
            )
            refs.append(
                [
                    {
                        "kind": "image_transcription",
                        "block_id": identifier,
                        "text_hash": by_id[identifier]["text_hash"],
                        "image_hash": by_id[identifier]["image_hash"],
                    }
                    for identifier in item.source_ids
                ]
            )
            tags.extend(tag for tag in item.tech_tags if tag not in tags)
        metadata["requirements"] = accepted
        if conflicts:
            metadata.update(status="partial", source_conflicts=conflicts)
        drafts = merged
        content = replace(content, skill_tags=tags)
    elif result is not None:
        limitations.append("jd_image_extraction_failed")
    metadata["limitations"] = list(dict.fromkeys(limitations))
    content = replace(
        content,
        source_limitations=list(dict.fromkeys(limitations)),
        source_metadata={**content.source_metadata, "image_extraction": metadata},
    )
    return ImageDrafts(content, drafts, refs)
