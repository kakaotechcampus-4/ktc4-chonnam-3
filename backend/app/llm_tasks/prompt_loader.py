"""활성 prompt version을 DB에서 읽어 AI 계약 값으로 변환한다."""

from devon_ai.contracts import PromptSpec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PromptNotFoundError(LookupError):
    """요청한 task에 활성 prompt version이 없을 때 발생한다."""


class PromptConfigurationError(RuntimeError):
    """DB의 활성 prompt 구성이 신뢰할 수 없을 때 발생한다."""


async def load_active_prompt(session: AsyncSession, task_name: str) -> PromptSpec:
    """활성 prompt 하나를 반환하며 DB session은 반환값에 포함하지 않는다.

    활성 행이 없거나 여러 개면 실패한다. 임시 본문이나 설정의 기본 모델로 대체하지 않는다.
    조회 transaction의 종료와 이후 모델 호출은 호출자가 관리한다.
    """

    normalized_task_name = task_name.strip()
    if not normalized_task_name:
        raise ValueError("task_name must not be blank")

    # 두 행까지만 읽어 중복 활성을 감지한다. 최신 행 하나를 골라 오류를 숨기지 않는다.
    result = await session.execute(
        text(
            """
            SELECT task_name, version, model, template
            FROM prompt_versions
            WHERE task_name = :task_name AND is_active IS TRUE
            ORDER BY updated_at DESC
            LIMIT 2
            """
        ),
        {"task_name": normalized_task_name},
    )
    rows = result.mappings().all()
    if not rows:
        raise PromptNotFoundError(f"active prompt not found for task: {normalized_task_name}")
    if len(rows) != 1:
        raise PromptConfigurationError(
            f"multiple active prompts found for task: {normalized_task_name}"
        )
    return PromptSpec(**rows[0])


__all__ = [
    "PromptConfigurationError",
    "PromptNotFoundError",
    "PromptSpec",
    "load_active_prompt",
]
