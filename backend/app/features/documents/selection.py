"""분석 실행에서 사용자가 명시적으로 선택한 소유 문서만 읽는다."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisJob, InterviewSession, UserDocument


async def selected_documents(
    db: AsyncSession, interview: InterviewSession
) -> tuple[UserDocument, ...]:
    run = await db.get(AnalysisJob, interview.analysis_job_id)
    if run is None or run.user_id != interview.user_id:
        return ()
    result = []
    for document_id, doc_type in (
        (run.document_id, "portfolio"),
        (run.cover_letter_document_id, "cover_letter"),
    ):
        if document_id is None:
            continue
        document = await db.scalar(
            select(UserDocument).where(
                UserDocument.id == document_id,
                UserDocument.user_id == interview.user_id,
                UserDocument.doc_type == doc_type,
            )
        )
        if document is not None:
            result.append(document)
    return tuple(result)
