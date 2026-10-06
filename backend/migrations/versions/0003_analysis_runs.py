"""분석 입력별 중복 제약과 후보 페이지 실행 지표.

Revision ID: 0003_analysis_runs
Revises: 0002_posting_versions
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_analysis_runs"
down_revision = "0002_posting_versions"
branch_labels = None
depends_on = None
ACTIVE = "status IN ('queued', 'running')"


def upgrade() -> None:
    op.drop_index("uq_analysis_jobs_active_user_job_type", table_name="analysis_jobs")
    op.create_index(
        "uq_analysis_jobs_active_user_job_type",
        "analysis_jobs",
        ["user_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(ACTIVE + " AND job_type <> 'analysis_run'"),
    )
    # 과거 fingerprint가 없는 행도 같은 사용자의 NULL끼리 중복되지는 않게 한다.
    op.create_index(
        "uq_analysis_jobs_active_fingerprint",
        "analysis_jobs",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text(ACTIVE + " AND job_type = 'analysis_run'"),
    )
    op.add_column(
        "analysis_repo_candidate_pages", sa.Column("started_at", sa.DateTime(timezone=True))
    )
    op.add_column("analysis_repo_candidate_pages", sa.Column("duration_ms", sa.Integer()))
    op.add_column("analysis_repo_candidate_pages", sa.Column("queue_wait_ms", sa.Integer()))


def downgrade() -> None:
    duplicates = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM analysis_jobs WHERE "
            + ACTIVE
            + " GROUP BY user_id, job_type HAVING count(*) > 1)"
        )
    )
    if duplicates:
        # 원래 제약을 복원하기 위해 진행 중인 사용자 작업을 임의 삭제하지 않는다.
        raise RuntimeError("Finish concurrent analysis runs before downgrading")
    for column in ("queue_wait_ms", "duration_ms", "started_at"):
        op.drop_column("analysis_repo_candidate_pages", column)
    op.drop_index("uq_analysis_jobs_active_fingerprint", table_name="analysis_jobs")
    op.drop_index("uq_analysis_jobs_active_user_job_type", table_name="analysis_jobs")
    op.create_index(
        "uq_analysis_jobs_active_user_job_type",
        "analysis_jobs",
        ["user_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
