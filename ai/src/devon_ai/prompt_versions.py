"""배포 식별자와 실행 코드의 지원 버전을 구분한다. 원본 식별자는 바꾸지 않는다."""

import re
from collections.abc import Collection

from devon_ai import contracts as c


def base_prompt_version(version: str) -> str:
    if (
        type(version) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:@[A-Za-z0-9][A-Za-z0-9_.-]*)?", version)
        is None
    ):
        raise c.ContractError("schema", "prompt version identity")
    return version.partition("@")[0]


def require_prompt_version(
    prompt: c.PromptSpec, *, task_name: str, supported_versions: Collection[str]
) -> None:
    if (
        type(prompt) is not c.PromptSpec
        or prompt.task_name != task_name
        or base_prompt_version(prompt.version) not in supported_versions
    ):
        raise c.ContractError("schema", "unsupported prompt version")
