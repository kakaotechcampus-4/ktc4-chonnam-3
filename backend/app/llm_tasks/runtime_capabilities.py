"""설치된 task 모듈의 출력 계약을 프롬프트 활성화 전에 확인한다."""

from collections.abc import Sequence
from importlib import import_module

from devon_ai import contracts as c
from devon_ai.prompt_versions import base_prompt_version

_TASK_MODULES = {
    "director": "devon_ai.agents.director.runtime",
    **{
        name: "devon_ai.llm_tasks." + name
        for name in (
            "repo_shallow",
            "repo_deep",
            "domain_category",
            "doc_claims",
            "claim_code",
            "jd_extract_image",
            "answer_analysis",
            "report_score",
            "report",
        )
    },
    "profile_summary": "app.llm_tasks.profile_summary",
}


def validate_runtime_prompts(prompts: Sequence[c.PromptSpec]) -> None:
    """미설치·미지원 항목이 있으면 DB 등록 전에 전체 요청을 거절한다."""
    for prompt in prompts:
        module_name = _TASK_MODULES.get(prompt.task_name)
        if module_name is None:
            raise c.ContractError("schema", "runtime task is not installed")
        try:
            module = import_module(module_name)
        except ImportError:
            raise c.ContractError("schema", "runtime consumer is not installed") from None
        versions = getattr(module, "SUPPORTED_PROMPT_VERSIONS", ())
        if base_prompt_version(prompt.version) not in versions:
            raise c.ContractError("schema", "runtime prompt is not supported by installed consumer")
        if prompt.task_name == "director":
            module.operation_prompts(prompt)
