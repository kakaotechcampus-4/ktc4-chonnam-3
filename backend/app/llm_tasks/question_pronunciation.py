"""정규화하지 못한 영어 구절만 한 번 요청해 한글 발음으로 바꾼다."""

import logging
import re
from dataclasses import replace
from typing import cast

from devon_ai.contracts import AttemptMetadata, ContractError, ModelRequest, PromptSpec
from devon_ai.prompt_versions import require_prompt_version

from app.core.config import LLMSettings
from app.integrations.llm.client import call_model
from app.integrations.tts.pronunciation import (
    COMBINING_MARKS,
    LATIN_CHARACTERS,
    SpeechFragment,
    is_latin_name,
)

QUESTION_PRONUNCIATION_TASK = "question_pronunciation"
QUESTION_PRONUNCIATION_TIMEOUT_SECONDS = 5.0
SUPPORTED_PROMPT_VERSIONS = frozenset({"question_pronunciation_v2"})

_MAX_FRAGMENTS = 12
_MAX_FRAGMENT_CHARS = 80
_MAX_CONTEXT_CHARS = 240
_KINDS = frozenset({"term", "acronym", "identifier", "domain", "path", "file", "extension"})
_FRAGMENT = re.compile(
    rf"[{LATIN_CHARACTERS}][{LATIN_CHARACTERS}{COMBINING_MARKS}]*"
    rf"(?:[ _'’\-][{LATIN_CHARACTERS}][{LATIN_CHARACTERS}{COMBINING_MARKS}]*){{0,7}}"
)
_UNMASKED_CONTEXT = re.compile(rf"[{LATIN_CHARACTERS}{COMBINING_MARKS}0-9/\\@]")
_SPOKEN = re.compile(r"[가-힣]+(?: [가-힣]+)*")
logger = logging.getLogger(__name__)


async def pronounce_fragments(
    settings: LLMSettings,
    prompt: PromptSpec,
    fragments: tuple[SpeechFragment, ...],
    *,
    attempt_sink: list[AttemptMetadata] | None = None,
) -> tuple[str, ...] | None:
    """검증한 발음을 입력 순서대로 돌려준다. 실패하면 호출자가 로컬 발화문을 사용한다."""
    if not fragments or len(fragments) > _MAX_FRAGMENTS:
        return None
    if any(
        type(fragment) is not SpeechFragment
        or not isinstance(fragment.text, str)
        or len(fragment.text) > _MAX_FRAGMENT_CHARS
        or not _FRAGMENT.fullmatch(fragment.text)
        or not all(is_latin_name(part) for part in re.split(r"[ _'’\-]", fragment.text))
        or not isinstance(fragment.kind, str)
        or fragment.kind not in _KINDS
        or not isinstance(fragment.context, str)
        or len(fragment.context) > _MAX_CONTEXT_CHARS
        or _UNMASKED_CONTEXT.search(fragment.context)
        or any(ord(char) < 32 and char not in "\n\r\t" for char in fragment.context)
        for fragment in fragments
    ):
        return None
    try:
        require_prompt_version(
            prompt,
            task_name=QUESTION_PRONUNCIATION_TASK,
            supported_versions=SUPPORTED_PROMPT_VERSIONS,
        )
    except ContractError:
        return None

    words = {
        f"f{index}": {"text": fragment.text, "kind": fragment.kind, "context": fragment.context}
        for index, fragment in enumerate(fragments, start=1)
    }

    def validate(output: object) -> tuple[str, ...]:
        if not isinstance(output, dict) or output.keys() != words.keys():
            raise ContractError("schema", "pronunciation fragment identifiers")
        values = cast(dict[str, object], output)
        pronunciations = []
        for key in words:
            value = values[key]
            if not isinstance(value, str):
                raise ContractError("schema", "pronunciation fragment type")
            if len(value) > _MAX_FRAGMENT_CHARS or not _SPOKEN.fullmatch(value):
                raise ContractError("semantic", "pronunciation fragment format")
            pronunciations.append(value)
        return tuple(pronunciations)

    limits = settings.call_limits(QUESTION_PRONUNCIATION_TASK)
    request = ModelRequest(
        prompt=prompt,
        payload={"fragments": words},
        schema_name=QUESTION_PRONUNCIATION_TASK,
        schema_version="question_pronunciation.v2",
        output_schema={
            "type": "object",
            "properties": {key: {"type": "string"} for key in words},
            "required": list(words),
            "additionalProperties": False,
        },
        limits=replace(
            limits,
            timeout_seconds=min(limits.timeout_seconds, QUESTION_PRONUNCIATION_TIMEOUT_SECONDS),
            max_output_tokens=min(limits.max_output_tokens, 1024),
            max_input_bytes=min(limits.max_input_bytes, 16384),
            max_response_bytes=min(limits.max_response_bytes, 65536),
            reasoning_effort="low",
        ),
        max_attempts=1,
    )
    result = await call_model(
        request,
        validate,
        api_key=settings.openai_api_key,
        base_url=settings.llm_base_url,
        attempt_sink=attempt_sink,
    )
    if result.failure is not None:
        logger.info(
            "question_pronunciation_fallback",
            extra={"failure_stage": result.failure.stage, "attempt_count": len(result.attempts)},
        )
    return result.data
