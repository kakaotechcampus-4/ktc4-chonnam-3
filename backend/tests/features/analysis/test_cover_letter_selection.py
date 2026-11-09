"""선택한 자소서만 소유권·종류를 확인해 분석 입력과 중복 판정에 연결한다."""

import hashlib
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.db.models import AnalysisJob, GithubAccount, User, UserDocument
from app.features.analysis import service
from app.features.analysis.run_schemas import CreateAnalysisRunRequest
from app.shared.enums import Reason


async def seed_documents(sessions):
    async with sessions.begin() as db:
        user, other = User(name="Owner"), User(name="Other owner")
        db.add_all([user, other])
        await db.flush()
        db.add(
            GithubAccount(
                user_id=user.id,
                github_user_id=501,
                login="owner",
                access_token_encrypted=b"isolated-fixture",
                token_status="valid",
            )
        )
        documents = {}
        for name, owner, doc_type, status in [
            ("portfolio", user, "portfolio", "succeeded"),
            ("letter", user, "cover_letter", "succeeded"),
            ("second_letter", user, "cover_letter", "partial"),
            ("failed_letter", user, "cover_letter", "failed"),
            ("other_letter", other, "cover_letter", "succeeded"),
        ]:
            document = UserDocument(
                user_id=owner.id,
                doc_type=doc_type,
                filename=name + ".pdf",
                mime_type="application/pdf",
                size_bytes=4,
                extract_status=status,
            )
            db.add(document)
            await db.flush()
            documents[name] = document.id
        return user.id, documents


async def start(sessions, user_id, **inputs):
    request = CreateAnalysisRunRequest(postingUrl="https://www.wanted.co.kr/wd/123", **inputs)
    async with sessions() as db:
        return await service.create_run(db, user_id, request, AsyncMock())


async def test_selected_letter_is_saved_separately_from_portfolio(session_factory, monkeypatch):
    user_id, documents = await seed_documents(session_factory)
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "enqueue_analysis", enqueue)

    run_id = await start(
        session_factory,
        user_id,
        documentId=documents["portfolio"],
        coverLetterDocumentId=documents["letter"],
    )
    async with session_factory() as db:
        run = await db.get(AnalysisJob, run_id)
        assert run.document_id == documents["portfolio"]
        assert run.cover_letter_document_id == documents["letter"]
    enqueue.assert_awaited_once()


async def test_letter_changes_input_identity_without_selecting_latest_document(
    session_factory, monkeypatch
):
    user_id, documents = await seed_documents(session_factory)
    monkeypatch.setattr(service, "enqueue_analysis", AsyncMock(return_value=True))
    inputs = {"documentId": documents["portfolio"]}
    first = await start(
        session_factory, user_id, **inputs, coverLetterDocumentId=documents["letter"]
    )
    second = await start(
        session_factory, user_id, **inputs, coverLetterDocumentId=documents["second_letter"]
    )
    without = await start(session_factory, user_id, **inputs)
    assert len({first, second, without}) == 3
    async with session_factory() as db:
        run = await db.get(AnalysisJob, without)
        assert run.cover_letter_document_id is None
        previous_input = [
            str(user_id),
            "https://www.wanted.co.kr/wd/123",
            str(documents["portfolio"]),
        ]
        assert (
            run.fingerprint
            == hashlib.sha256(
                json.dumps(previous_input, separators=(",", ":")).encode()
            ).hexdigest()
        )

    with pytest.raises(AppError) as error:
        await start(session_factory, user_id, **inputs, coverLetterDocumentId=documents["letter"])
    assert error.value.reason == Reason.RUN_IN_PROGRESS
    assert error.value.details["runId"] == str(first)


@pytest.mark.parametrize(
    "selection,expected",
    [
        ("other_letter", Reason.INVALID_REQUEST),
        ("portfolio", Reason.INVALID_REQUEST),
        ("failed_letter", Reason.DOCUMENT_EXTRACT_FAILED),
        ("missing", Reason.INVALID_REQUEST),
    ],
)
async def test_invalid_letter_is_rejected_before_enqueue(
    session_factory, monkeypatch, selection, expected
):
    user_id, documents = await seed_documents(session_factory)
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "enqueue_analysis", enqueue)
    with pytest.raises(AppError) as error:
        await start(
            session_factory,
            user_id,
            coverLetterDocumentId=documents.get(selection, uuid4()),
        )
    assert error.value.reason == expected
    enqueue.assert_not_awaited()


async def test_letter_alone_does_not_become_portfolio_selection_hint(session_factory, monkeypatch):
    user_id, documents = await seed_documents(session_factory)
    monkeypatch.setattr(service, "enqueue_analysis", AsyncMock(return_value=True))
    run_id = await start(session_factory, user_id, coverLetterDocumentId=documents["letter"])
    async with session_factory() as db:
        run = await db.get(AnalysisJob, run_id)
        assert run.document_id is None
        assert run.cover_letter_document_id == documents["letter"]
        assert (
            next(step for step in run.steps if step["key"] == "doc_extract")["status"] == "pending"
        )


@pytest.mark.parametrize("with_portfolio", [False, True])
@pytest.mark.parametrize("mutation", [None, "owner", "type", "failed"])
async def test_worker_validates_selected_letter_without_using_it_as_repo_hint(
    session_factory, redis, monkeypatch, with_portfolio, mutation
):
    from types import SimpleNamespace

    from app.features.analysis.pipeline import run as pipeline
    from app.features.analysis.pipeline.run_support import RunFailure

    user_id, documents = await seed_documents(session_factory)
    monkeypatch.setattr(service, "enqueue_analysis", AsyncMock(return_value=True))
    inputs = {"coverLetterDocumentId": documents["letter"]}
    if with_portfolio:
        inputs["documentId"] = documents["portfolio"]
    run_id = await start(session_factory, user_id, **inputs)
    async with session_factory.begin() as db:
        letter = await db.get(UserDocument, documents["letter"])
        letter.extracted_github_urls = ["https://github.com/letter/not-a-hint"]
        if mutation == "owner":
            letter.user_id = (await db.get(UserDocument, documents["other_letter"])).user_id
        elif mutation == "type":
            letter.doc_type = "portfolio"
        elif mutation == "failed":
            letter.extract_status = "failed"
        if with_portfolio:
            (await db.get(UserDocument, documents["portfolio"])).extracted_github_urls = [
                "https://github.com/portfolio/verified"
            ]
    observed = []

    async def stop_after_document(db, selected_run, *, portfolio_full_names, min_size_kb):
        observed.append(portfolio_full_names)
        raise RunFailure("no_public_repo")

    monkeypatch.setattr(pipeline, "prepare_candidates", stop_after_document)
    await pipeline.run_analysis(
        {
            "session_factory": session_factory,
            "redis": redis,
            "settings": SimpleNamespace(analysis_run_ttl_seconds=3600, repo_min_size_kb=0),
        },
        run_id,
    )
    async with session_factory() as db:
        run = await db.get(AnalysisJob, run_id)
        state = next(item["status"] for item in run.steps if item["key"] == "doc_extract")
        if mutation is None:
            assert state == "completed"
            assert observed == [["portfolio/verified"] if with_portfolio else []]
            assert run.error_code == "no_public_repo"
        else:
            assert state == "failed" and run.error_code == "doc_extract_failed"
            assert observed == []
