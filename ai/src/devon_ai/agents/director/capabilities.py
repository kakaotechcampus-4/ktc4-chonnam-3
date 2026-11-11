"""Director 배포 버전별 내부 입력·검증 기능의 단일 기준."""

from dataclasses import dataclass

from devon_ai import contracts as c


@dataclass(frozen=True)
class DirectorCapabilities:
    turn_state: bool = False
    bounded_ids: bool = False
    recovery_feedback: bool = False
    projected_input: bool = False
    follow_up_policy: bool = False
    reuse_empty_lookup_analysis: bool = False
    structured_dialogue: bool = False
    auto_replan: bool = False
    operation_prompts: bool = False
    required_point_review: bool = False
    stable_point_review: bool = False
    source_bound_contract: bool = False


_CAPABILITIES = {
    **{f"director_v{number}": DirectorCapabilities() for number in range(1, 5)},
    "director_v5": DirectorCapabilities(turn_state=True),
    "director_v6": DirectorCapabilities(turn_state=True, bounded_ids=True),
    **{
        f"director_v{number}": DirectorCapabilities(
            turn_state=True, bounded_ids=True, recovery_feedback=True
        )
        for number in (7, 8)
    },
    **{
        f"director_v{number}": DirectorCapabilities(
            turn_state=True,
            bounded_ids=True,
            recovery_feedback=True,
            projected_input=True,
            follow_up_policy=True,
            reuse_empty_lookup_analysis=True,
        )
        for number in (9, 10, 11)
    },
    **{
        f"director_v{number}": DirectorCapabilities(
            turn_state=True,
            bounded_ids=True,
            recovery_feedback=True,
            projected_input=True,
            follow_up_policy=True,
            reuse_empty_lookup_analysis=True,
            structured_dialogue=True,
            auto_replan=True,
            operation_prompts=number in (13, 14, 16, 17),
            required_point_review=number in (14, 15, 16, 17),
            stable_point_review=number in (16, 17),
            source_bound_contract=number == 17,
        )
        for number in (12, 13, 14, 15, 16, 17)
    },
}
SUPPORTED_PROMPT_VERSIONS = frozenset(_CAPABILITIES)


def prompt_capabilities(version: str) -> DirectorCapabilities:
    """배포 suffix는 허용하되 알 수 없는 버전을 기존 기능으로 추정하지 않는다."""
    capability = _CAPABILITIES.get(version.partition("@")[0])
    if capability is None:
        raise c.ContractError("schema", "unsupported Director prompt version")
    return capability
