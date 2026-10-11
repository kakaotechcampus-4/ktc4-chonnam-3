"""업로드 경로를 제외한 표시용 파일명이 PostgreSQL에 저장되는지 검증한다."""

import io

import pytest
from fastapi import UploadFile

from app.db.models.document import UserDocument
from app.db.models.user import User
from app.features.documents.service import preview_document


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("포트폴리오.TXT", "포트폴리오.TXT"),
        ("/home/member/포트폴리오.TXT", "포트폴리오.TXT"),
        (r"C:\fakepath\포트폴리오.TXT", "포트폴리오.TXT"),
        (r"C:\folder/subfolder\포트폴리오.TXT", "포트폴리오.TXT"),
        ("/private\x00/포트\x00폴리오.TXT", "포트폴리오.TXT"),
        ("이력" * 200 + ".txt", "이력" * 200 + ".txt"),
    ],
    ids=["unchanged", "posix", "windows", "mixed", "nul", "long"],
)
async def test_preview_stores_only_display_filename(db, filename, expected):
    user = User(name="Document owner")
    db.add(user)
    await db.commit()
    # multipart 인코딩으로 NUL이 바뀌지 않도록 서비스에 실제 문자열을 전달한다.
    upload = UploadFile(io.BytesIO(b"Portfolio"), filename=filename)

    response = await preview_document(db, user, upload, max_file_bytes=100, max_text_chars=100)

    document = await db.get(UserDocument, response.document_id)
    assert document is not None
    assert document.filename == expected
    assert document.extracted_text == "Portfolio"
    assert document.extract_status == "succeeded"
    assert upload.file.closed
