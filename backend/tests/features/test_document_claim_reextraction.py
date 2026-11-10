"""재추출은 전체 주장이 같은 경우만 재사용하며 과거 대조의 근거를 보존한다."""

from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from devon_ai.llm_tasks.doc_claims import ClaimExtraction
from devon_ai.llm_tasks.doc_claims import DocumentClaim as AIClaim
from sqlalchemy import select

from app.db.models import (
    DocumentClaim,
    DocumentClaimComparison,
    InterviewSession,
    PromptVersion,
    UserDocument,
)
from app.features.documents import claims
from app.features.documents.claim_comparison import (
    load_claim_comparison_sources,
    prepare_selected_claim_comparisons,
)
from app.features.documents.source_snapshot import claim_location
from tests.features.test_document_claim_comparison import provider, seed
from tests.features.test_document_claim_lifecycle import selected as selected
from tests.features.test_document_claim_lifecycle import settings


async def activate(app, version):
    async with app.state.session_factory.begin() as db:
        for prompt in await db.scalars(
            select(PromptVersion).where(PromptVersion.task_name == "doc_claims")
        ):
            prompt.is_active = False
        await db.flush()
        db.add(
            PromptVersion(
                task_name="doc_claims",
                version=version,
                model="test",
                template="claims",
                is_active=True,
            )
        )


@pytest.mark.parametrize("field", ["claim_type", "tech_tags", "source_text", "source_location"])
async def test_reextraction_matches_all_fields_and_finds_matching_history(
    app, selected, monkeypatch, field
):
    interview_id, job_id, ids = selected
    calls = []
    claim_type, tags = "role", ("OldTag",)

    async def extract(text, **kwargs):
        calls.append(text)
        return ClaimExtraction((AIClaim(text, claim_type, tags, 0, text),), None, ())

    monkeypatch.setattr(claims, "analyze_document_claims", extract)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory.begin() as db:
        old_ids = []
        for document_id in ids[:2]:
            document = await db.get(UserDocument, document_id)
            old_id = UUID(document.claims_active_ids[0])
            old_ids.append(old_id)
            old = await db.get(DocumentClaim, old_id)
            if field == "source_text":
                old.source_text = "legacy source line"
            elif field == "source_location":
                old.source_location = {"start_line": 99, "end_line": 99}
        old_values = [
            deepcopy(getattr(await db.get(DocumentClaim, item), field)) for item in old_ids
        ]
    if field == "claim_type":
        claim_type = "implementation"
    elif field == "tech_tags":
        tags = ("NewTag",)
    await activate(app, "doc_claims_v2")
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        active_ids = [(await db.get(UserDocument, item)).claims_active_ids for item in ids[:2]]
        assert all(current != [str(old)] for current, old in zip(active_ids, old_ids, strict=True))
    await activate(app, "doc_claims_v3")
    for _ in range(2):
        await claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    assert len(calls) == 6
    async with app.state.session_factory() as db:
        assert len(list(await db.scalars(select(DocumentClaim)))) == 4
        for document_id, current, old_id, old_value in zip(
            ids[:2], active_ids, old_ids, old_values, strict=True
        ):
            assert (await db.get(UserDocument, document_id)).claims_active_ids == current
            assert getattr(await db.get(DocumentClaim, old_id), field) == old_value


async def test_corrected_claim_type_recompares_without_changing_history(app, monkeypatch):
    interview_id, job_id, old_id, document_id, evidence_id = await seed(app, claim_type="role")
    await activate(app, "doc_claims_v1")
    async with app.state.session_factory.begin() as db:
        document = await db.get(UserDocument, document_id)
        document.claims_prompt_version = "doc_claims_v1"
        old = await db.get(DocumentClaim, old_id)
        old.paragraph_no = 0
        old.tech_tags = ["OldTag"]
        old.source_location = claim_location(document.source_snapshot, 0, old.source_text)
    await prepare_selected_claim_comparisons(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        old_comparison = await db.scalar(select(DocumentClaimComparison))
        history = deepcopy((old_comparison.claim_source, old_comparison.result))
        comparison_id = old_comparison.id
        assert old_comparison.status == "unverified"
    await activate(app, "doc_claims_v2")

    async def corrected(text, **kwargs):
        return ClaimExtraction((AIClaim(text, "implementation", ("NewTag",), 0, text),), None, ())

    monkeypatch.setattr(claims, "analyze_document_claims", corrected)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        current_id = UUID((await db.get(UserDocument, document_id)).claims_active_ids[0])
        assert current_id != old_id
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(current_id, evidence_id, calls))
    ) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    assert len(calls) == 1
    async with app.state.session_factory() as db:
        previous = await db.get(DocumentClaimComparison, comparison_id)
        assert (previous.claim_source, previous.result) == history
        assert (await db.get(DocumentClaim, old_id)).claim_type == "role"
        comparisons = list(await db.scalars(select(DocumentClaimComparison)))
        assert len(comparisons) == 2
        current = next(item for item in comparisons if item.claim_id == current_id)
        assert (
            current.status == "consistent"
            and current.input_fingerprint != previous.input_fingerprint
        )
        sources = await load_claim_comparison_sources(
            db, await db.get(InterviewSession, interview_id)
        )
        assert len(sources) == 1 and sources[0].source_id == str(current.id)
