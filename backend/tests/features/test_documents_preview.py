"""실제 세션·PostgreSQL을 통한 포트폴리오 preview 계약."""

import asyncio
import importlib
import io
import threading
from uuid import UUID

import pytest
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.errors import AppError
from app.db.models.document import DocumentClaim, UserDocument
from app.db.models.user import User
from tests.integrations.test_extract import build_blank_pdf, build_docx, build_pdf


@pytest.fixture
async def member(db, app, client):
    user = User(name="Document owner")
    db.add(user)
    await db.commit()
    sid = await app.state.sessions.create(user.id)
    client.cookies.set("devon_session", sid)
    return user


async def stored(db, response):
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"documentId", "extractStatus"}
    document = await db.get(UserDocument, UUID(response.json()["documentId"]))
    assert document is not None, "Response ID must identify a committed document"
    return document


@pytest.mark.parametrize(
    ("filename", "data", "mime"),
    [
        ("PORTFOLIO.PDF", build_pdf("github.com/alice/repo/tree/main"), "application/pdf"),
        (
            "portfolio.docx",
            build_docx(["github.com/alice/repo"]),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("portfolio.txt", b"github.com/alice/repo", "text/plain"),
        ("portfolio.md", b"# Portfolio\ngithub.com/alice/repo", "text/markdown"),
    ],
    ids=["pdf", "docx", "txt", "md"],
)
async def test_four_formats_persist_owned_metadata_and_minimal_response(
    client, member, db, filename, data, mime
):
    response = await client.post(
        "/api/documents/preview", files={"file": (filename, data, "application/octet-stream")}
    )
    document = await stored(db, response)
    assert response.json()["extractStatus"] == "succeeded"
    assert document.user_id == member.id
    assert document.doc_type == "portfolio"
    assert document.filename == filename
    assert document.mime_type == mime
    assert document.size_bytes == len(data)
    assert document.extracted_github_urls == ["alice/repo"]
    assert document.extract_error_code is None
    assert document.is_truncated is False
    assert await db.scalar(select(func.count()).select_from(DocumentClaim)) == 0


async def test_success_does_not_require_a_github_url(client, member, db):
    response = await client.post(
        "/api/documents/preview", files={"file": ("portfolio.txt", b"Hello portfolio")}
    )
    document = await stored(db, response)
    assert document.extract_status == "succeeded"
    assert document.extracted_text == "Hello portfolio"
    assert document.extracted_github_urls == []


@pytest.mark.parametrize(
    ("filename", "data", "error"),
    [
        ("scan.pdf", build_blank_pdf(), "no_text_layer"),
        ("broken.pdf", b"broken", "corrupted_file"),
        ("broken.docx", b"broken", "corrupted_file"),
        ("empty.txt", b" \n", "empty_document"),
        ("empty.md", b"", "empty_document"),
    ],
    ids=["scan", "corrupt_pdf", "corrupt_docx", "empty_txt", "empty_md"],
)
async def test_unreadable_supported_documents_still_return_a_persisted_id(
    client, member, db, filename, data, error
):
    response = await client.post("/api/documents/preview", files={"file": (filename, data)})
    document = await stored(db, response)
    assert response.json()["extractStatus"] == "failed"
    assert document.extract_status == "failed"
    assert document.extract_error_code == error
    assert document.extracted_text is None
    assert document.extracted_github_urls == []


async def test_partial_persists_bounded_text_all_urls_and_nul_cleanup(client, member, db, app):
    app.state.settings.documents_max_text_chars = 100
    source = b"Beginning\x00\n" + b"Filler.\n" * 200 + b"github.com/alice/end"
    response = await client.post("/api/documents/preview", files={"file": ("long.txt", source)})
    document = await stored(db, response)
    assert document.extract_status == "partial"
    assert document.is_truncated is True
    assert "\x00" not in document.extracted_text
    assert len(document.extracted_text) <= 100
    assert document.extracted_github_urls == ["alice/end"]


@pytest.mark.parametrize(
    "filename", ["image.png", "document.hwp", "slides.pptx", "file", "file.markdown"]
)
async def test_mime_cannot_bypass_unsupported_extension(client, member, db, filename):
    response = await client.post(
        "/api/documents/preview", files={"file": (filename, b"text", "application/pdf")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["reason"] == "unsupported_document_type"
    assert await db.scalar(select(func.count()).select_from(UserDocument)) == 0


@pytest.mark.parametrize(("size", "status"), [(20_971_520, 200), (20_971_521, 413)])
async def test_actual_file_size_limit_is_inclusive(client, member, db, size, status):
    response = await client.post(
        "/api/documents/preview", files={"file": ("large.txt", b"A" * size)}
    )
    assert response.status_code == status
    if status == 200:
        document = await stored(db, response)
        assert document.size_bytes == size
        assert document.extract_status == "partial"
    else:
        assert response.json()["error"]["reason"] == "document_too_large"
        assert await db.scalar(select(func.count()).select_from(UserDocument)) == 0


async def test_preview_requires_session(client, db):
    response = await client.post(
        "/api/documents/preview", files={"file": ("portfolio.txt", b"text")}
    )
    assert response.status_code == 401
    assert response.json()["error"]["reason"] == "unauthenticated"
    assert await db.scalar(select(func.count()).select_from(UserDocument)) == 0


async def test_preview_uses_configured_file_limit(client, member, app):
    app.state.settings.max_upload_bytes_portfolio = 3
    response = await client.post("/api/documents/preview", files={"file": ("a.txt", b"four")})
    assert response.status_code == 413


async def test_missing_file_uses_error_envelope(client, member):
    response = await client.post("/api/documents/preview", data={"postingUrl": "not accepted"})
    assert response.status_code == 400
    assert response.json()["error"]["reason"] == "invalid_request"


@pytest.mark.parametrize(
    ("filename", "data", "reason"),
    [
        ("a.txt", b"text", None),
        ("a.png", b"text", "unsupported_document_type"),
        ("a.txt", b"large", "document_too_large"),
    ],
)
async def test_upload_is_closed_and_reported_size_cannot_override_actual_bytes(
    db, member, filename, data, reason
):
    from app.features.documents.service import preview_document

    upload = UploadFile(io.BytesIO(data), filename=filename, size=0)
    if reason:
        with pytest.raises(AppError) as caught:
            await preview_document(db, member, upload, max_file_bytes=4, max_text_chars=100)
        assert caught.value.reason.value == reason
    else:
        response = await preview_document(db, member, upload, max_file_bytes=4, max_text_chars=100)
        document = await db.get(UserDocument, response.document_id)
        assert document.size_bytes == 4
    assert upload.file.closed


async def test_extraction_runs_outside_event_loop(client, member, db, monkeypatch):
    module = importlib.import_module("app.features.documents.service")
    actual = module.process_document
    loop_thread = threading.get_ident()
    extraction_threads = []

    def record_thread(*args, **kwargs):
        extraction_threads.append(threading.get_ident())
        return actual(*args, **kwargs)

    monkeypatch.setattr(module, "process_document", record_thread)
    response = await client.post("/api/documents/preview", files={"file": ("a.txt", b"text")})
    await stored(db, response)
    assert extraction_threads and loop_thread not in extraction_threads
    await asyncio.sleep(0)


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("programming error"), OperationalError("write", {}, Exception("db down"))],
)
async def test_unexpected_failures_are_not_reported_as_successful_failed_documents(
    client, member, db, monkeypatch, failure
):
    module = importlib.import_module("app.features.documents.service")
    if isinstance(failure, OperationalError):

        async def fail_commit(self):
            raise failure

        monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.commit", fail_commit)
    else:

        def fail_extract(*args, **kwargs):
            raise failure

        monkeypatch.setattr(module, "process_document", fail_extract)
    response = await client.post("/api/documents/preview", files={"file": ("a.txt", b"text")})
    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
    assert await db.scalar(select(func.count()).select_from(UserDocument)) == 0
