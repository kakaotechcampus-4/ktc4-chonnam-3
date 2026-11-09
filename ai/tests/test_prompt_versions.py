"""배포 식별자는 보존하면서 실제 지원하는 wire 버전만 실행한다."""

import pytest

from devon_ai import contracts as c
from devon_ai.prompt_versions import base_prompt_version, require_prompt_version


@pytest.mark.parametrize("version", ["task_v1", "task_v1@luna-review-20261109"])
def test_base_version_validation_preserves_full_prompt_identity(version):
    prompt = c.PromptSpec("task", version, "configured-model", "policy")
    require_prompt_version(prompt, task_name="task", supported_versions={"task_v1"})
    assert base_prompt_version(version) == "task_v1"
    assert prompt.version == version


@pytest.mark.parametrize(
    "version",
    ["", "@deployment", "task_v1@", "task_v1@x@y", "task_v1\n", "task_v1@bad value", None, True],
)
def test_invalid_deployment_identity_is_not_accepted_as_a_supported_version(version):
    with pytest.raises(c.ContractError):
        base_prompt_version(version)


def test_unknown_base_and_wrong_task_are_rejected_without_changing_prompt():
    prompt = c.PromptSpec("task", "task_v9@deployment", "configured-model", "policy")
    with pytest.raises(c.ContractError):
        require_prompt_version(prompt, task_name="task", supported_versions={"task_v1"})
    with pytest.raises(c.ContractError):
        require_prompt_version(prompt, task_name="other", supported_versions={"task_v9"})
    assert prompt.version == "task_v9@deployment"
