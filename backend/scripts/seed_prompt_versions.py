"""외부에서 검수된 prompt 본문을 재실행해도 중복 없이 등록한다."""

from collections.abc import Iterable

from devon_ai.contracts import PromptSpec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROMPT_VERSIONS = {
    "repo_shallow": "repo_shallow_v1",
    "repo_deep": "repo_deep_v1",
    "jd_extract": "jd_extract_v1",
    "answer_analysis": "answer_analysis_v1",
    "director": "director_v1",
    "report": "report_v1",
    "profile_summary": "profile_summary_v1",
}


class PromptSeedValidationError(ValueError):
    """검수 입력이 초기 seed 또는 부분 등록 조건을 만족하지 않을 때 발생한다."""


class PromptVersionConflictError(RuntimeError):
    """같은 version 이름에 다른 model 또는 본문이 들어왔을 때 발생한다."""


async def seed_prompt_versions(session: AsyncSession, prompts: Iterable[PromptSpec]) -> None:
    """검수된 고정 일곱 v1 prompt를 등록하고 활성화한다."""

    prompt_list = list(prompts)
    _validate_prompts(prompt_list)
    await register_prompt_versions(session, prompt_list)


async def register_prompt_versions(session: AsyncSession, prompts: Iterable[PromptSpec]) -> None:
    """검수된 task별 명시적 version을 등록하고 해당 task만 활성 전환한다.

    호출자는 하나의 transaction 안에서 실행하고 commit/rollback을 관리한다.
    task별 PostgreSQL transaction 잠금으로 초기 seed와 부분 등록의 활성화 경합을 직렬화한다.
    기존 task/version의 모델과 본문은 덮어쓰지 않고 다르면 충돌로 처리한다.
    모델이나 본문을 바꿀 때는 새 version을 지정해야 이전 분석 캐시와 구분할 수 있다.
    """

    prompt_list = list(prompts)
    _validate_registration(prompt_list)
    # 여러 task의 잠금을 항상 같은 순서로 잡아 초기 seed와 부분 등록의 교착을 피한다.
    prompt_list.sort(key=lambda prompt: prompt.task_name)

    for prompt in prompt_list:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:task_name))"),
            {"task_name": prompt.task_name},
        )

    # 어떤 행도 변경하기 전에 전체 입력의 기존 버전 충돌부터 검사한다.
    existing = {}
    for prompt in prompt_list:
        result = await session.execute(
            text(
                """
                SELECT model, template, is_active
                FROM prompt_versions
                WHERE task_name = :task_name AND version = :version
                FOR UPDATE
                """
            ),
            {"task_name": prompt.task_name, "version": prompt.version},
        )
        row = result.mappings().one_or_none()
        if row is not None and (row["model"] != prompt.model or row["template"] != prompt.template):
            raise PromptVersionConflictError(
                f"prompt version already exists with different content: "
                f"{prompt.task_name}/{prompt.version}"
            )
        existing[(prompt.task_name, prompt.version)] = row

    for prompt in prompt_list:
        current = existing[(prompt.task_name, prompt.version)]
        params = {
            "task_name": prompt.task_name,
            "version": prompt.version,
            "model": prompt.model,
            "template": prompt.template,
        }
        await session.execute(
            text(
                """
                UPDATE prompt_versions
                SET is_active = FALSE, updated_at = now()
                WHERE task_name = :task_name
                  AND version <> :version
                  AND is_active IS TRUE
                """
            ),
            params,
        )
        if current is not None and current["is_active"]:
            # 동일한 활성 버전을 재등록해도 원래 행과 갱신 시각을 보존한다.
            continue
        if current is None:
            await session.execute(
                text(
                    """
                    INSERT INTO prompt_versions
                        (task_name, version, model, template, is_active)
                    VALUES
                        (:task_name, :version, :model, :template, TRUE)
                    """
                ),
                params,
            )
        else:
            await session.execute(
                text(
                    """
                    UPDATE prompt_versions
                    SET is_active = TRUE, updated_at = now()
                    WHERE task_name = :task_name AND version = :version
                    """
                ),
                params,
            )


def _validate_prompts(prompts: list[PromptSpec]) -> None:
    expected = set(PROMPT_VERSIONS.items())
    actual = {(prompt.task_name, prompt.version) for prompt in prompts}
    if len(prompts) != len(expected) or actual != expected:
        raise PromptSeedValidationError("exactly the seven fixed task/version pairs are required")


def _validate_registration(prompts: list[PromptSpec]) -> None:
    if not prompts:
        raise PromptSeedValidationError("at least one reviewed prompt is required")
    seen: set[str] = set()
    for prompt in prompts:
        if prompt.task_name not in PROMPT_VERSIONS:
            raise PromptSeedValidationError(f"unknown prompt task: {prompt.task_name}")
        if prompt.task_name in seen:
            raise PromptSeedValidationError(
                f"only one version per task is allowed: {prompt.task_name}"
            )
        seen.add(prompt.task_name)
        for field in ("version", "model", "template"):
            if not getattr(prompt, field).strip():
                raise PromptSeedValidationError(f"{field} must not be blank: {prompt.task_name}")


__all__ = [
    "PROMPT_VERSIONS",
    "PromptSeedValidationError",
    "PromptVersionConflictError",
    "register_prompt_versions",
    "seed_prompt_versions",
]
