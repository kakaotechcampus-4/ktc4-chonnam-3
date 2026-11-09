"""질문한 공고의 이미지 전사를 코드 근거와 분리해 복원한다."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict

from devon_ai import contracts as c

from app.db.models import InterviewTurn, JdRequirement, JobPosting
from app.features.interview.agent_context import _domain_limitations


def jd_source_notes(
    posting: JobPosting | None,
    requirements: list[JdRequirement],
    turns: list[InterviewTurn],
) -> tuple[list[dict[str, object]], list[str]]:
    raw = posting.raw_payload or {} if posting is not None else {}
    limitations = list(_domain_limitations(raw))
    asked = {str(item) for turn in turns for item in turn.jd_requirement_ids}
    for turn in turns:
        basis = (turn.question_contract or {}).get("basis_refs", [])
        for ref in basis if isinstance(basis, list) else []:
            if isinstance(ref, dict) and ref.get("kind") == "jd_requirement":
                asked.add(str(ref.get("id")))
    blocks = raw.get("source_blocks", [])
    blocks = blocks if isinstance(blocks, list) else []
    counts = Counter(str(item.get("block_id")) for item in blocks if isinstance(item, dict))
    by_id = {
        str(item.get("block_id")): item
        for item in blocks
        if isinstance(item, dict) and counts[str(item.get("block_id"))] == 1
    }
    notes: list[dict[str, object]] = []
    remaining, seen = 16384, set()
    for requirement in requirements:
        identifier = str(requirement.id)
        if identifier not in asked:
            continue
        refs = requirement.source_refs or []
        if len(refs) > 8:
            limitations.append(f"jd_source_reference_limit:{identifier}")
        for reference in refs[:8]:
            if not isinstance(reference, dict):
                limitations.append(f"jd_source_unavailable:{identifier}:invalid_reference")
                continue
            block_id = reference.get("block_id")
            key = identifier, str(block_id)
            if key in seen:
                continue
            seen.add(key)
            block = by_id.get(str(block_id))
            failure = f"jd_source_unavailable:{identifier}:{block_id}"
            if reference.get("kind") != "image_transcription" or block is None:
                limitations.append(failure + ":missing_or_ambiguous_block")
                continue
            text = block.get("text")
            if (
                not isinstance(text, str)
                or not text.strip()
                or reference.get("text_hash") != block.get("text_hash")
                or reference.get("image_hash") != block.get("image_hash")
                or hashlib.sha256(text.encode()).hexdigest() != block.get("text_hash")
            ):
                limitations.append(failure + ":hash_mismatch")
                continue
            if remaining <= 0:
                limitations.append(f"jd_source_context_budget_exceeded:{identifier}:{block_id}")
                continue
            excerpt = text.encode()[: min(4096, remaining)].decode("utf-8", errors="ignore")
            if not excerpt.strip():
                limitations.append(f"jd_source_context_budget_exceeded:{identifier}:{block_id}")
                continue
            partial = excerpt != text
            note_limits = [
                *limitations,
                "job_posting_requirement_not_candidate_implementation_evidence",
                "ocr_transcription_not_verified_against_image",
            ]
            location = {key: block[key] for key in ("image_url", "page", "element") if key in block}
            if partial:
                # 블록 좌표는 전체 전사에만 대응한다. prefix의 실제 좌표 구간은 추정하지 않는다.
                location["location_scope"] = "block_only_excerpt_span_unknown"
                note_limits.append("jd_source_context_excerpt")
                limitations.append("jd_source_context_excerpt")
            elif "coordinate" in block:
                location["coordinate"] = block["coordinate"]
            try:
                note = c.JDSourceNote(
                    identifier,
                    str(block_id),
                    "job_posting.source_blocks",
                    excerpt,
                    json.dumps(location, ensure_ascii=False, sort_keys=True, allow_nan=False),
                    str(block["text_hash"]),
                    str(block["image_hash"]),
                    tuple(dict.fromkeys(note_limits)),
                    "prefix_excerpt" if partial else "entire_block",
                )
            except (c.ContractError, ValueError, TypeError):
                limitations.append(failure + ":invalid_block")
                continue
            notes.append(json.loads(json.dumps(asdict(note))))
            remaining -= len(excerpt.encode())
    return notes, list(dict.fromkeys(limitations))
