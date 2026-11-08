"""이미지 공고 전사의 출처·미확인 범위를 리포트에 전달한다."""

import hashlib
import json
from uuid import uuid4

import pytest

from app.db.models import InterviewTurn, JdRequirement, JobPosting
from app.features.report import service


def payload(*, text="Python 개발 경험", absent=False, mismatch=False):
    posting_id, requirement_id = uuid4(), uuid4()
    block = {
        "block_id": "I0-P1-E0",
        "text": text,
        "text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "image_hash": "a" * 64,
        "image_url": "https://static.wanted.co.kr/posting.png",
        "page": 1,
        "element": 0,
        "coordinate": [0, 1, 2, 3],
    }
    posting = JobPosting(
        id=posting_id,
        raw_payload={
            "source_blocks": [] if absent else [block],
            "_image_extraction": {
                "limitations": ["image_count_limit", "image_structured_category_conflict"]
            },
        },
    )
    requirement = JdRequirement(
        id=requirement_id,
        job_posting_id=posting_id,
        text="Python 개발 경험",
        category="required",
        source_refs=[
            {
                "kind": "image_transcription",
                "block_id": block["block_id"],
                "text_hash": "b" * 64 if mismatch else block["text_hash"],
                "image_hash": block["image_hash"],
            }
        ],
    )
    unasked = JdRequirement(
        id=uuid4(), text="미질문", category="preferred", source_refs=requirement.source_refs
    )
    turn = InterviewTurn(
        id=uuid4(),
        turn_no=1,
        persona="tech_lead",
        question_text="경험을 설명해 주세요",
        answer_text="설명",
        jd_requirement_ids=[requirement_id],
        question_contract={"basis_refs": []},
    )
    data = service._build_payload(
        posting, [turn], {}, [requirement, unasked], dict.fromkeys(service.SCORE_KEYS, {})
    )
    return data, str(requirement_id), block


def test_only_asked_image_jd_source_is_preserved_separately_from_code_evidence():
    data, identifier, block = payload()
    assert data["requirements"][0]["source_field"] == "job_posting.source_blocks"
    notes = data["source_notes"]
    assert len(notes) == 1 and notes[0]["requirement_id"] == identifier
    assert notes[0]["content"] == block["text"]
    assert notes[0]["text_hash"] == block["text_hash"]
    assert json.loads(notes[0]["location"])["coordinate"] == [0, 1, 2, 3]
    assert notes[0]["read_scope"] == "entire_block"
    assert "jd_image:image_count_limit" in data["limitations"]
    assert "jd_image:image_structured_category_conflict" in data["limitations"]
    assert data["turns"][0]["evidences"] == []


@pytest.mark.parametrize("options", [{"absent": True}, {"mismatch": True}])
def test_missing_or_mismatched_original_is_an_explicit_limitation(options):
    data, identifier, _ = payload(**options)
    assert data["source_notes"] == []
    assert any(
        value.startswith(f"jd_source_unavailable:{identifier}:") for value in data["limitations"]
    )


def test_source_excerpt_does_not_claim_the_whole_original_coordinate_span():
    data, _, block = payload(text="Python 개발 경험\n" + "한" * 3000)
    note = data["source_notes"][0]
    assert len(note["content"].encode()) <= 4096
    assert block["text"].startswith(note["content"])
    assert note["read_scope"] == "prefix_excerpt"
    assert "coordinate" not in json.loads(note["location"])
    assert "jd_source_context_excerpt" in note["limitations"]
    assert "jd_source_context_excerpt" in data["limitations"]
