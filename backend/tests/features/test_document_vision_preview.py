"""실제 Vision 어댑터와 preview·원문 보존 경계를 HTTP 대역으로 연결한다."""

from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.db.models import GithubAccount, User, UserDocument
from app.integrations.vision.elice import EliceVisionClient, EliceVisionSettings
from tests.integrations.test_extract import build_pdf


async def test_configured_image_ocr_preserves_transcription_and_original_layout(client, db, app):
    owner = User(name="OCR owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    calls = []

    def provider(request):
        calls.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "pages": [
                        {
                            "elements": [
                                {
                                    "label": "text",
                                    "content": "문서에 적힌 구현 내용",
                                    "description": "모델이 생성한 해석",
                                    "coordinate": [1, 2, 3, 4],
                                }
                            ]
                        }
                    ]
                },
            },
        )

    app.state.vision_client = EliceVisionClient(
        EliceVisionSettings(
            base_url="https://example.mlapi.run",
            api_key=SecretStr("test"),
            poll_interval_seconds=0.001,
        ),
        transport=httpx.MockTransport(provider),
    )
    response = await client.post(
        "/api/documents/preview", files={"file": ("portfolio.png", b"image", "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["extractStatus"] == "succeeded"
    document = await db.get(UserDocument, UUID(response.json()["documentId"]))
    assert "문서에 적힌 구현 내용" in document.source_snapshot["text"]
    assert "모델이 생성한 해석" not in document.source_snapshot["text"]
    assert document.source_snapshot["blocks"][0]["page"] == 1
    assert document.source_snapshot["blocks"][0]["coordinate"] == [1, 2, 3, 4]
    assert len(calls) == 2


async def test_native_text_does_not_call_vision_even_when_configured(client, db, app):
    owner = User(name="Text owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))

    def forbidden(request):
        raise AssertionError("Native text caused unnecessary OCR request")

    app.state.vision_client = EliceVisionClient(
        EliceVisionSettings(base_url="https://example.mlapi.run", api_key=SecretStr("test")),
        transport=httpx.MockTransport(forbidden),
    )
    response = await client.post(
        "/api/documents/preview", files={"file": ("portfolio.txt", b"native text", "text/plain")}
    )
    assert response.status_code == 200
    assert response.json()["extractStatus"] == "succeeded"


async def test_mlapi_console_vision_setting_is_connected_to_preview(client, db, app, monkeypatch):
    from app.features.documents import router

    owner = User(name="Legacy vision configuration owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    app.state.settings.helpy_vision_document_proxy_url = "https://example.mlapi.run/model/v1"
    app.state.settings.proxy_token = SecretStr("legacy-proxy-secret")
    seen = []

    def provider(request):
        seen.append(request.url.path)
        assert request.headers["authorization"] == "Bearer legacy-proxy-secret"
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "legacy-config"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "pages": [
                        {
                            "elements": [
                                {
                                    "label": "text",
                                    "content": "Synthetic source",
                                    "bounding_box": [1, 2, 30, 40],
                                }
                            ]
                        }
                    ],
                },
            },
        )

    monkeypatch.setattr(
        router,
        "EliceVisionClient",
        lambda settings: EliceVisionClient(settings, transport=httpx.MockTransport(provider)),
    )
    response = await client.post(
        "/api/documents/preview",
        files={
            "file": ("synthetic.png", b"image", "image/png"),
        },
    )
    assert response.status_code == 200 and response.json()["extractStatus"] == "succeeded"
    document = await db.get(UserDocument, UUID(response.json()["documentId"]))
    assert document.source_snapshot["text"] == "Synthetic source"
    assert document.source_snapshot["blocks"][0]["coordinate"] == [1, 2, 30, 40]
    assert seen == ["/model/v1/documents", "/model/v1/jobs/legacy-config"]


async def test_native_pdf_title_still_requests_layout_and_preserves_ocr_table(client, db, app):
    owner = User(name="Mixed PDF owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    calls = []

    def provider(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "mixed-job", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "pages": [
                        {
                            "elements": [
                                {"label": "title", "content": "Project title"},
                                {
                                    "label": "table",
                                    "content": "Latency 15ms",
                                    "coordinate": [1, 2, 3, 4],
                                },
                            ],
                        }
                    ]
                },
            },
        )

    app.state.vision_client = EliceVisionClient(
        EliceVisionSettings(
            base_url="https://example.mlapi.run",
            api_key=SecretStr("test"),
            poll_interval_seconds=0.001,
        ),
        transport=httpx.MockTransport(provider),
    )
    response = await client.post(
        "/api/documents/preview",
        files={
            "file": ("portfolio.pdf", build_pdf("Project title"), "application/pdf"),
        },
    )
    assert response.status_code == 200
    document = await db.get(UserDocument, UUID(response.json()["documentId"]))
    assert "Project title" in document.source_snapshot["text"]
    assert "Latency 15ms" in document.source_snapshot["text"]
    assert document.source_snapshot["text"].count("Project title") == 1
    assert document.source_snapshot["blocks"][1]["coordinate"] == [1, 2, 3, 4]
    assert calls == ["POST", "GET"]


async def test_pdf_layout_supplement_can_be_explicitly_disabled(client, db, app):
    owner = User(name="Native PDF owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    app.state.settings.vision_pdf_layout = False

    def forbidden(request):
        raise AssertionError("Layout was explicitly disabled")

    app.state.vision_client = EliceVisionClient(
        EliceVisionSettings(base_url="https://example.mlapi.run", api_key=SecretStr("test")),
        transport=httpx.MockTransport(forbidden),
    )
    response = await client.post(
        "/api/documents/preview",
        files={
            "file": ("portfolio.pdf", build_pdf("Project title"), "application/pdf"),
        },
    )
    assert response.status_code == 200
    assert response.json()["extractStatus"] == "succeeded"


@pytest.mark.parametrize(
    "filename,data,status",
    [
        ("portfolio.txt", b"native text", "succeeded"),
        ("portfolio.pdf", build_pdf("Project title"), "partial"),
        ("portfolio.png", b"image", "failed"),
    ],
)
async def test_invalid_optional_vision_configuration_preserves_native_content(
    client, db, app, filename, data, status
):
    owner = User(name="Invalid vision config owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    app.state.settings.vision_base_url = "invalid-private-url"
    app.state.settings.vision_api_key = SecretStr("private-key")

    response = await client.post("/api/documents/preview", files={"file": (filename, data)})

