"""공식 원문의 독립 불변 저장과 면접별 출처 연결."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0014_official_source_snapshots"
down_revision = "0013_prompt_version_capacity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "official_source_snapshots",
        sa.Column(
            "id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("catalog_key", sa.String(100), nullable=False),
        sa.Column("catalog_hash", sa.String(64), nullable=False),
        sa.Column("domain_categories", pg.JSONB(), nullable=False),
        sa.Column("technology", sa.String(100), nullable=False),
        sa.Column("technology_version", sa.String(100), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("section_heading", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("page_content", sa.Text(), nullable=False),
        sa.Column("page_content_hash", sa.String(64), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", pg.JSONB(), nullable=False),
        sa.Column("limitations", pg.JSONB(), nullable=False),
        sa.CheckConstraint("start_line > 0 AND end_line >= start_line", name="line_range"),
        sa.CheckConstraint(
            "char_length(content_hash) = 64 AND char_length(page_content_hash) = 64 "
            "AND char_length(catalog_hash) = 64",
            name="hashes",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_key",
            "catalog_hash",
            "page_content_hash",
            "retrieved_at",
            name="uq_official_snapshot",
        ),
    )
    op.create_index(
        "ix_official_snapshot_catalog_retrieved",
        "official_source_snapshots",
        ["catalog_key", "retrieved_at"],
    )
    op.add_column(
        "interview_external_sources",
        sa.Column("official_snapshot_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_external_source_official_snapshot",
        "interview_external_sources",
        "official_source_snapshots",
        ["official_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # 갱신 시 기존 인용의 원문을 바꾸지 않고 새 snapshot을 추가한다. 삭제도 원문 보존을 따른다.
    op.execute("""CREATE FUNCTION reject_official_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'official source snapshots are immutable'; END; $$""")
    op.execute("""CREATE TRIGGER official_snapshot_immutable BEFORE UPDATE OR DELETE
        ON official_source_snapshots FOR EACH ROW
        EXECUTE FUNCTION reject_official_snapshot_mutation()""")


def downgrade():
    # DDL은 불변 trigger를 거치지 않으므로 원문·인용을 잠근 뒤 존재 여부부터 확인한다.
    op.execute(
        "LOCK TABLE official_source_snapshots, interview_external_sources IN ACCESS EXCLUSIVE MODE"
    )
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM official_source_snapshots) OR EXISTS "
            "(SELECT 1 FROM interview_external_sources WHERE official_snapshot_id IS NOT NULL)"
        )
    ):
        raise RuntimeError("Preserve official source snapshots and citations before downgrade")
    op.drop_constraint(
        "fk_external_source_official_snapshot", "interview_external_sources", type_="foreignkey"
    )
    op.drop_column("interview_external_sources", "official_snapshot_id")
    op.drop_table("official_source_snapshots")
    op.execute("DROP FUNCTION reject_official_snapshot_mutation()")
