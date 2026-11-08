"""문서·웹 원문을 면접 소유권과 버전에 맞춰 읽는 실제 DB 검사."""

import hashlib
from datetime import UTC, datetime

from app.db.models import DocumentClaim, InterviewExternalSource, UserDocument
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


async def test_document_claim_and_web_source_remain_separate_and_owned(db):
    from app.features.interview.supplemental_sources import load_supplemental_sources

    owner = await make_user(db)
    outsider = await make_user(db)
    run = await make_run(db, owner)
    repo = await make_repo(db, run)
    version = hashlib.sha256(b"document").hexdigest()
    document = UserDocument(
        user_id=owner.id,
        filename="portfolio.txt",
        doc_type="portfolio",
        mime_type="text/plain",
        size_bytes=8,
        extracted_text="document",
        extracted_github_urls=[],
        extract_status="succeeded",
        is_truncated=False,
        source_snapshot={"text_hash": version, "limitations": []},
    )
    db.add(document)
    await db.flush()
    run.document_id = document.id
    claim = DocumentClaim(
        document_id=document.id,
        claim_text="구현했다고 주장함",
        source_text="document",
        source_version=version,
        source_location={"start_line": 1, "end_line": 1},
    )
    db.add(claim)
    interview = await make_interview(db, run, [repo])
    for user in (owner, outsider):
        db.add(
            InterviewExternalSource(
                user_id=user.id,
                interview_session_id=interview.id,
                query_text="reference",
                url=f"https://elice.io/{user.id}",
                title="Official reference",
                content="web text",
                content_scope="extracted_page",
                content_hash=hashlib.sha256(b"web text").hexdigest(),
                retrieved_at=datetime.now(UTC),
                limitations=[],
            )
        )
    await db.commit()
    sources = await load_supplemental_sources(db, interview.id)
    assert {source.kind for source in sources} == {"document_claim", "external_source"}
    assert len(sources) == 2
    document_source = next(source for source in sources if source.kind == "document_claim")
    assert document_source.version == version
    assert "확인된 개인 기여" not in document_source.content
    assert "document_claim_unverified" in document_source.limitations


async def test_stale_document_claim_is_not_reused_as_current_source(db):
    from app.features.interview.supplemental_sources import load_supplemental_sources

    owner = await make_user(db)
    run = await make_run(db, owner)
    repo = await make_repo(db, run)
    document = UserDocument(
        user_id=owner.id,
        filename="portfolio.txt",
        doc_type="portfolio",
        mime_type="text/plain",
        size_bytes=3,
        extracted_text="new",
        extracted_github_urls=[],
        extract_status="succeeded",
        is_truncated=False,
        source_snapshot={"text_hash": hashlib.sha256(b"new").hexdigest()},
    )
    db.add(document)
    await db.flush()
    run.document_id = document.id
    stale = DocumentClaim(
        document_id=document.id,
        claim_text="old",
        source_text="old",
        source_version=hashlib.sha256(b"old").hexdigest(),
    )
    db.add(stale)
    interview = await make_interview(db, run, [repo])
    await db.commit()
    assert await load_supplemental_sources(db, interview.id) == ()
    from devon_ai import contracts as c

    archived = await load_supplemental_sources(
        db, interview.id, source_refs=frozenset({c.BasisRef("document_claim", str(stale.id))})
    )
    assert len(archived) == 1 and archived[0].version == hashlib.sha256(b"old").hexdigest()
    assert "historical_document_claim" in archived[0].limitations
