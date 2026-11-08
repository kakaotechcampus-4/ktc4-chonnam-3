"""리포트 실행권·버전·검토 이력과 프로필 입력 지문."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0010_report_review_runtime"
down_revision = "0009_jd_image_sources"
branch_labels = None
depends_on = None


def _identity():
    return [
        sa.Column(
            "id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.add_column(
        "interview_reports",
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "user_profile_summaries", sa.Column("input_fingerprint", sa.String(64), nullable=True)
    )
    for column in [
        sa.Column("source_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
    ]:
        op.add_column("report_disagreements", column)
    op.drop_constraint(
        "uq_report_disagreements_report_persona", "report_disagreements", type_="unique"
    )
    op.create_unique_constraint(
        "uq_report_disagreements_revision_persona",
        "report_disagreements",
        ["report_id", "source_revision", "persona"],
    )
    op.create_table(
        "report_revisions",
        *_identity(),
        sa.Column(
            "report_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("interview_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "revision", name="uq_report_revisions_version"),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
    )
    # 기존 성공 리포트를 최초 불변 버전으로 옮기고 현재 공개 결과는 변경하지 않는다.
    op.execute("""
        INSERT INTO report_revisions (report_id, revision, snapshot)
        SELECT r.id, 1, to_jsonb(r) || jsonb_build_object('scores', COALESCE(
          (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.score_key)
           FROM report_scores s WHERE s.report_id=r.id), '[]'::jsonb))
        FROM interview_reports r
    """)
    op.create_table(
        "report_generation_requests",
        *_identity(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "interview_session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("expected_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "disagreement_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_disagreements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("input_fingerprint", sa.String(64), nullable=True),
        sa.Column("input_snapshot", pg.JSONB(), nullable=True),
        sa.Column("attempts", pg.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("mode IN ('initial', 'retry', 'reassessment')", name="mode"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'stale', 'enqueue_failed')",
            name="status",
        ),
        sa.CheckConstraint("expected_revision >= 0", name="expected_revision"),
    )
    op.create_index(
        "uq_report_generation_active",
        "report_generation_requests",
        ["interview_session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM report_generation_requests) "
            "OR EXISTS (SELECT 1 FROM interview_reports WHERE current_revision > 1) "
            "OR EXISTS (SELECT 1 FROM report_revisions WHERE revision > 1) "
            "OR EXISTS (SELECT 1 FROM report_disagreements WHERE reviewed_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Report review history must be preserved before downgrade")
    op.drop_table("report_generation_requests")
    op.drop_table("report_revisions")
    op.drop_constraint(
        "uq_report_disagreements_revision_persona", "report_disagreements", type_="unique"
    )
    op.create_unique_constraint(
        "uq_report_disagreements_report_persona", "report_disagreements", ["report_id", "persona"]
    )
    for column in (
        "applied_revision",
        "reviewed_at",
        "review_reason",
        "reviewed_by",
        "status",
        "source_revision",
    ):
        op.drop_column("report_disagreements", column)
    op.drop_column("user_profile_summaries", "input_fingerprint")
    op.drop_column("interview_reports", "current_revision")
