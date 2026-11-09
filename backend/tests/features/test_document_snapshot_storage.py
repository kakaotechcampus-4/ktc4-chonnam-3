"""실제 업로드에서 축약되지 않은 원문이 별도로 저장되는지 검증한다."""

from uuid import UUID

from app.db.models.document import UserDocument
from app.db.models.user import User


async def test_preview_truncation_does_not_replace_preserved_source(client, db, app):
    owner = User(name="Source owner")
    db.add(owner)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
    app.state.settings.documents_max_text_chars = 20
    text = "프로젝트 설명\n" + "실제로 수행한 구현 내용\n" * 80
    response = await client.post(
        "/api/documents/preview", files={"file": ("portfolio.txt", text.encode(), "text/plain")}
    )
    assert response.status_code == 200
    document = await db.get(UserDocument, UUID(response.json()["documentId"]))
    assert document is not None
    assert len(document.extracted_text) <= 20
    assert document.source_snapshot["text"] == text.strip()
    assert "partial_extraction" not in document.source_snapshot["limitations"]
    assert document.claims_status == "pending"
