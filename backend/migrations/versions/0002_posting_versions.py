"""동일 URL의 공고 변경 내용을 기존 테이블 안에서 새 ID로 보존한다."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_posting_versions"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_job_postings_normalized_url", "job_postings", type_="unique")
    op.create_index(
        "ix_job_postings_url_created_at", "job_postings", ["normalized_url", "created_at"]
    )


def downgrade() -> None:
    # 자료를 지워 UNIQUE를 복구하면 과거 면접의 근거를 잃는다. DDL 전체를 롤백한다.
    # 사전 확인과 제약 복구 사이의 새 버전 INSERT도 차단한다.
    op.execute("LOCK TABLE job_postings IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM job_postings GROUP BY normalized_url HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION '공고 이력이 존재하여 URL UNIQUE를 복구할 수 없습니다';
            END IF;
        END $$
    """)
    op.create_unique_constraint(
        "uq_job_postings_normalized_url", "job_postings", ["normalized_url"]
    )
    op.drop_index("ix_job_postings_url_created_at", table_name="job_postings")
