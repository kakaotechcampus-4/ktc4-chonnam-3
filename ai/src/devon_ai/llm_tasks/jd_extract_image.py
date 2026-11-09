"""이미지 전사에서 원문으로 검증되는 JD 항목만 채택한다. 수집·DB는 BE가 소유한다."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from devon_ai import contracts as c

SUPPORTED_PROMPT_VERSIONS = frozenset({"jd_extract_image_v1"})


Category = Literal["required", "preferred", "responsibility"]
_HEADINGS = {
    "required": (
        r"자격\s*요건|지원\s*자격|필수(?:\s*요건|\s*사항)?"
        r"|required(?: qualifications)?|requirements"
    ),
    "preferred": r"우대(?:\s*사항|\s*조건)?|preferred(?: qualifications)?",
    "responsibility": r"주요\s*업무|담당\s*업무|responsibilities",
}


@dataclass(frozen=True)
class ImageRequirement:
    category: Category
    text: str
    tech_tags: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ImageJdResult:
    requirements: tuple[ImageRequirement, ...]
    rejected: tuple[str, ...]
    limitations: tuple[str, ...]


def _heading(text: str, excerpt: str) -> set[str]:
    # 같은 블록에 여러 절이 있으면 인용한 문장 앞의 마지막 명시 제목만 확인한다.
    prefix = text[: text.find(excerpt)] if excerpt in text else text
    found = []
    for category, pattern in _HEADINGS.items():
        for match in re.finditer(r"^\s*(?:" + pattern + r")\s*[:：]?\s*$", prefix, re.I | re.M):
            found.append((match.start(), category))
    return {max(found)[1]} if found else set()


def _technology_in(tag: str, text: str) -> bool:
    # Go를 Google의 일부로, SQL을 MySQL의 일부로 채택하지 않는다.
    flags = 0 if tag.casefold() in {"go", "r", "c"} else re.I
    return (
        re.search(r"(?<![A-Za-z0-9_+#])" + re.escape(tag) + r"(?![A-Za-z0-9_+#])", text, flags)
        is not None
    )


def parse_image_requirements(
    payload: object, blocks: Mapping[str, str], *, max_requirements: int = 20
) -> ImageJdResult:
    if not isinstance(payload, dict) or set(payload) != {"requirements", "limitations"}:
        raise c.ContractError("schema", "image requirements")
    items, limitations = payload["requirements"], payload["limitations"]
    if (
        not isinstance(items, list)
        or len(items) > max_requirements
        or not isinstance(limitations, list)
        or any(type(note) is not str for note in limitations)
    ):
        raise c.ContractError("schema", "image requirements")
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"category", "text", "tech_tags", "source_ids"}
            or type(item["category"]) is not str
            or item["category"] not in _HEADINGS
            or type(item["text"]) is not str
            or not item["text"].strip()
        ):
            raise c.ContractError("schema", "image requirement")
        for key, limit in (("tech_tags", 10), ("source_ids", 8)):
            value = item[key]
            if (
                not isinstance(value, list)
                or len(value) > limit
                or any(type(text) is not str or not text.strip() for text in value)
                or (key == "source_ids" and not value)
            ):
                raise c.ContractError("schema", key)
    accepted, rejected = [], []
    seen = set()
    for index, item in enumerate(items):
        refs = tuple(dict.fromkeys(item["source_ids"]))
        text = item["text"].strip()
        if any(ref not in blocks for ref in refs):
            rejected.append(f"item_{index}:unknown_source")
            continue
        originals = [blocks[ref] for ref in refs]
        tags = tuple(dict.fromkeys(tag.strip() for tag in item["tech_tags"]))
        headings = set().union(*(_heading(original, text) for original in originals))
        if not any(text in original for original in originals) or any(
            not any(_technology_in(tag, original) for original in originals) for tag in tags
        ):
            rejected.append(f"item_{index}:unsupported_text_or_technology")
            continue
        if len(headings) != 1 or item["category"] not in headings:
            rejected.append(f"item_{index}:category_source_ambiguous")
            continue
        identity = (item["category"], text)
        if identity not in seen:
            seen.add(identity)
            accepted.append(ImageRequirement(cast(Category, item["category"]), text, tags, refs))
    return ImageJdResult(tuple(accepted), tuple(rejected), tuple(dict.fromkeys(limitations)))


async def extract_image_requirements(
    blocks: Mapping[str, str],
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[ImageJdResult],
    max_requirements: int = 20,
) -> c.ModelResult[ImageJdResult]:
    if prompt.task_name != "jd_extract_image" or not blocks or not 1 <= max_requirements <= 20:
        return c.ModelResult(
            None,
            c.CallFailure("semantic", "jd_image_input_invalid", "Image JD input rejected."),
            (),
        )
    item = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(_HEADINGS)},
            "text": {"type": "string"},
            "tech_tags": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "source_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(blocks)},
                "minItems": 1,
                "maxItems": 8,
            },
        },
        "required": ["category", "text", "tech_tags", "source_ids"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {
            "requirements": {"type": "array", "items": item, "maxItems": max_requirements},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["requirements", "limitations"],
        "additionalProperties": False,
    }
    return await model_call(
        c.ModelRequest(
            prompt,
            {
                "blocks": [{"id": key, "text": value} for key, value in blocks.items()],
                "max_requirements": max_requirements,
            },
            "ImageJdRequirements",
            "1",
            schema,
            limits,
        ),
        lambda raw: parse_image_requirements(raw, blocks, max_requirements=max_requirements),
    )
