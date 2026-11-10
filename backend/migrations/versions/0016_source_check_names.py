"""기존 원문·문서 대조 CHECK의 이중 접두를 정의 변경 없이 정렬한다."""

import sqlalchemy as sa
from alembic import op

revision = "0016_source_check_names"
down_revision = "0015_voice_ai_merge"
branch_labels = None
depends_on = None

_NAMES = (
    (
        "interview_external_sources",
        "ck_interview_external_sources_ck_interview_external_sou_3072",
        "ck_interview_external_sources_content_scope",
    ),
    (
        "document_claim_comparisons",
        "ck_document_claim_comparisons_ck_document_claim_compari_640b",
        "ck_document_claim_comparisons_status",
    ),
    (
        "document_claim_comparisons",
        "ck_document_claim_comparisons_ck_document_claim_compari_a60c",
        "ck_document_claim_comparisons_execution_status",
    ),
)


def _rename(table: str, before: str, after: str) -> None:
    names = set(
        op.get_bind().scalars(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid=to_regclass(:table) AND contype='c'"
            ),
            {"table": table},
        )
    )
    if after in names and before not in names:
        return
    if before not in names or after in names:
        raise RuntimeError("Source CHECK constraints require an unambiguous existing definition")
    # 고정된 식별자의 이름만 바꾼다. CHECK를 삭제·재생성하거나 행을 갱신하지 않는다.
    op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{before}" TO "{after}"')


def upgrade() -> None:
    for table, legacy, expected in _NAMES:
        _rename(table, legacy, expected)


def downgrade() -> None:
    for table, legacy, expected in reversed(_NAMES):
        _rename(table, expected, legacy)
