"""Sprint 1 프로필 집계·개인 역할 요약의 BE 경계.

완료 면접에 사용된 저장소를 중복 제거하고 저장소별 언어 비율을 같은 비중으로 평균낸다.
언어·프로젝트 유형 집계에는 LLM을 사용하지 않으며 개인 역할 요약만 LLM으로 생성한다.
기존 role_summary 저장 필드·roleSummary 응답과 report 성공 후 갱신·실패 분리를 유지한다.
기존 근거가 뒷받침하지 않는 개인 기여를 만들어내거나 프로젝트 설명을 개인 역할로 단정하지 않는다.
언어 자료가 없는 저장소를 0%로 채우거나 제외하지 않고 실패시켜 이전 성공 요약을 유지한다.

spec/ai/decisions/0016-profile-language-aggregation.md
spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md · docs/task-16-report.md
"""

import uuid
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from typing import cast

from devon_ai import contracts as c

from app.llm_tasks.report import ModelCall

ROLE_SUMMARY_MAX_CHARS = 500
# 면접 진술에 없는 단정은 개인 기여를 부풀리기 쉬워 진술에 나온 말일 때만 허용한다.
ABSOLUTE_CLAIMS = ("혼자", "단독", "전담", "전적으로", "도맡", "전부 직접", "모든 기능")
RATIO_DIGITS = 3


class ProfileSummaryError(RuntimeError):
    """프로필 갱신 실패. code 는 로그용이며 원문 예외 메시지·LLM 출력은 담지 않는다."""

    code = "profile_summary_failed"


class LanguageDataMissingError(ProfileSummaryError):
    code = "language_data_missing"


class RoleSummaryInvalidError(ProfileSummaryError):
    code = "role_summary_invalid"


class RoleSummaryCallError(ProfileSummaryError):
    code = "role_summary_call_failed"


class RoleEvidenceMissingError(ProfileSummaryError):
    """면접 진술이 없으면 역할을 추측해 채우지 않고 실패한다."""

    code = "role_evidence_missing"


def based_repo_ids(repo_ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    """중복 제거 후 정렬한 저장소 id. 재생성 판정 키라서 순서가 흔들리면 안 된다."""
    return sorted(set(repo_ids))


def aggregate_languages(
    languages_by_repo: Mapping[uuid.UUID, Mapping[str, int] | None],
) -> list[dict[str, object]]:
    """저장소별 언어 비율의 동일 비중 평균을 [{name, ratio}] (ratio 는 0~100) 로 만든다.

    저장소 하나의 언어 자료가 없거나 유효하지 않으면 0% 로 채우지 않고 실패한다.
    특정 언어가 없는 것은 0% 이며 분모를 줄이지 않는다. 코드량·면접 수로 가중하지 않는다.
    """
    if not languages_by_repo:
        raise LanguageDataMissingError("no repositories")
    totals: dict[str, float] = {}
    for languages in languages_by_repo.values():
        sizes = _valid_sizes(languages)
        whole = sum(sizes.values())
        for name, size in sizes.items():
            totals[name] = totals.get(name, 0.0) + size / whole
    count = len(languages_by_repo)
    ratios = {name: share / count * 100 for name, share in totals.items()}
    return [
        {"name": name, "ratio": round(ratio, RATIO_DIGITS)}
        for name, ratio in sorted(ratios.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _valid_sizes(languages: Mapping[str, int] | None) -> dict[str, int]:
    if not isinstance(languages, Mapping):
        raise LanguageDataMissingError("languages missing")
    sizes: dict[str, int] = {}
    for name, size in languages.items():
        if not isinstance(name, str) or isinstance(size, bool) or not isinstance(size, int):
            raise LanguageDataMissingError("languages invalid")
        if size < 0:
            raise LanguageDataMissingError("languages invalid")
        if size > 0:
            sizes[name] = size
    if not sizes:
        raise LanguageDataMissingError("languages empty")
    return sizes


def aggregate_project_types(types_by_repo: Mapping[uuid.UUID, Collection[str]]) -> list[str]:
    """저장소 수가 많은 유형 순, 같으면 이름 순. 한 저장소 안의 중복은 한 번만 센다."""
    counts: Counter[str] = Counter()
    for types in types_by_repo.values():
        counts.update({text.strip() for text in types if text.strip()})
    return [name for name, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]


def _output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"role_summary": {"type": "string"}},
        "required": ["role_summary"],
        "additionalProperties": False,
    }


def validate_role_summary(raw: object, statements: Iterable[str]) -> str:
    """모델 출력이 저장 가능한 역할 요약인지 코드로 검사한다. 보정해서 저장하지 않는다.

    빈 값·길이 초과와, 면접 진술에 나오지 않은 단정 표현을 거부한다.
    """
    if not isinstance(raw, Mapping) or set(raw) != {"role_summary"}:
        raise RoleSummaryInvalidError("shape")
    text = raw["role_summary"]
    if not isinstance(text, str) or not text.strip():
        raise RoleSummaryInvalidError("empty")
    text = text.strip()
    if len(text) > ROLE_SUMMARY_MAX_CHARS:
        raise RoleSummaryInvalidError("too_long")
    said = "\n".join(statements)
    if any(claim in text and claim not in said for claim in ABSOLUTE_CLAIMS):
        raise RoleSummaryInvalidError("unsupported_claim")
    return text


async def generate_role_summary(
    payload: dict[str, object],
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: ModelCall,
    statements: Iterable[str],
) -> str:
    """역할 요약만 LLM 으로 생성한다. 호출·검증 실패는 예외이며 기존 요약을 바꾸지 않는다.

    statements 는 payload 에 넣은 면접 진술 원문이다. 통계는 payload 로만 전달하고
    모델 출력에서는 role_summary 외 필드를 받지 않아 집계 결과를 바꿀 수 없다.
    """
    request = c.ModelRequest(
        prompt=prompt,
        payload=payload,
        schema_name="ProfileRoleSummary",
        schema_version="1",
        output_schema=_output_schema(),
        limits=limits,
    )
    kept = list(statements)

    def validator(raw: object) -> str:
        try:
            return validate_role_summary(raw, kept)
        except RoleSummaryInvalidError:
            # call_model 은 ContractError 만 출력 검증 실패로 보고 1회 재요청한다.
            raise c.ContractError("semantic", "role_summary") from None

    result = await model_call(request, validator)
    if result.failure is not None or result.data is None:
        raise RoleSummaryCallError(result.failure.error_code if result.failure else "no_data")
    return cast(str, result.data)
