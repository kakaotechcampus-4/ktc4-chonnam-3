"""추출 결과만 저장한다. 업로드 바이너리와 claim은 저장하지 않는다."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import UserDocument


async def insert_document(db: AsyncSession, document: UserDocument) -> None:
    db.add(document)
    await db.flush()
