"""score_criteria, prompt_versions, domain_question_frames.

topic_taxonomy / interview_personas / probe_patterns 는 Sprint 1 에 만들지 않는다.
CHECK 값, prompt, seed config 로 흡수한다 (docs/db-schema.md 주요 결정).

프롬프트·루브릭·domain frame 을 코드에 하드코딩하지 않기 위한 테이블이다
(docs/layer-rules.md 금지 목록).

docs/db-schema.md / task-02
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, check_in
from app.db.models.posting import DOMAIN_CATEGORIES
from app.db.models.report import SCORE_KEYS

# task-03 이 정한 3축. domain 별로 축마다 1개씩 3개를 시드한다.
QUESTION_FRAME_AXES = (
    "privacy_sensitive_data",
    "reliability_operations",
    "user_experience_context",
)


class ScoreCriterion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """점수 항목 기준. label_ko 가 리포트 응답의 scores[].label 이 된다.

    세부 기준 문구는 평가 담당 자료 보강에 따라 갱신될 수 있다.
    """

    __tablename__ = "score_criteria"
    __table_args__ = (
        UniqueConstraint("score_key", name="uq_score_criteria_score_key"),
        CheckConstraint(check_in("score_key", SCORE_KEYS), name="score_criteria_key"),
    )

    score_key: Mapped[str] = mapped_column(String(30), nullable=False)
    label_ko: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 구간별 채점 기준. 형식은 평가 자료 보강에 맞춰 바뀔 수 있어 JSONB 로 둔다.
    rubric: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class PromptVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """작업별 프롬프트 버전. 어느 모델·어느 프롬프트로 만든 결과인지의 원천이다.

    model 을 코드 상수로 두지 않고 여기서 읽는다 (Sprint 1 기본값 5.5 Luna).
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("task_name", "version", name="uq_prompt_versions_task_version"),
        # task 당 활성 버전 1개.
        Index(
            "uq_prompt_versions_active_per_task",
            "task_name",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    task_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DomainQuestionFrame(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """domain_lead 페르소나의 질문 뼈대. JD 요구사항 추궁이 아니라 도메인 관점이다."""

    __tablename__ = "domain_question_frames"
    __table_args__ = (
        UniqueConstraint(
            "domain_category", "axis", "display_order", name="uq_domain_frames_category_axis_order"
        ),
        CheckConstraint(
            check_in("domain_category", DOMAIN_CATEGORIES), name="domain_frames_category"
        ),
        CheckConstraint(check_in("axis", QUESTION_FRAME_AXES), name="domain_frames_axis"),
    )

    domain_category: Mapped[str] = mapped_column(String(20), nullable=False)
    axis: Mapped[str] = mapped_column(String(40), nullable=False)
    frame_text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
