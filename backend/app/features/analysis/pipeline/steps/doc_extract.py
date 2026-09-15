"""step 1 · 첨부 문서 반영.

Sprint 1 은 preview 문서에서 추출한 GitHub URL 만 analysis context 에 반영한다.
claim 추출은 하지 않는다 (document_claims 는 테이블만 존재, Sprint 2).
문서 실패는 hard blocker 가 아니다 — 문서 없이 공고만으로 계속 진행한다.

spec/backend/features/analysis-run.md 단계 1 / task-09
"""

import structlog

from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext
from app.integrations.extract.github_urls import normalize_repo_url
from app.shared.enums import DocumentExtractStatus

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """documentId 가 있으면 extracted_github_urls 를 owner/repo 로 정규화해 담는다."""
    ctx.portfolio_full_names = []
    if ctx.job.document_id is None:
        return

    document = await queries.get_document(ctx.db, ctx.job.document_id, ctx.user.id)
    if document is None:
        logger.warning("doc_extract_document_missing", run_id=str(ctx.job.id))
        return
    if document.extract_status == DocumentExtractStatus.FAILED:
        # 추출 실패도 진행을 막지 않는다 (FE 가 '계속 진행' 을 이미 선택한 상태).
        logger.info("doc_extract_skipped", run_id=str(ctx.job.id), reason="extract_failed")
        return

    names: list[str] = []
    for url in document.extracted_github_urls:
        full_name = normalize_repo_url(url)
        if full_name and full_name not in names:
            names.append(full_name)
    ctx.portfolio_full_names = names
    logger.info("doc_extract_done", run_id=str(ctx.job.id), mentioned=len(names))
