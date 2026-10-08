"""README 축약만 있는 L1 결과의 재사용 근거를 기록한다."""

import hashlib
import json
from dataclasses import asdict

from devon_ai import contracts as c

from app.db.models.github import RepoAnalysis

_PROOF_KEY = "_truncation_cache"


def _input_hash(source: c.ShallowRepoInput) -> str:
    # 원문을 복사 저장하지 않고, 분석에 실제 전달한 모든 입력을 같은 순서로 비교한다.
    payload = json.dumps(
        {"version": 1, "input": asdict(source)}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _truncation_only(source: c.ShallowRepoInput) -> bool:
    return (
        source.readme_truncated and source.readme_text is not None and not source.collection_errors
    )


def record_truncation_cache(values: dict[str, object], source: c.ShallowRepoInput) -> None:
    """검증된 L1을 축약 사유로 partial 저장할 때만 재사용 근거를 붙인다."""
    result = values.get("result")
    if (
        values.get("status") == "partial"
        and values.get("error_code") is None
        and isinstance(result, dict)
        and _truncation_only(source)
    ):
        # BE 저장 전용 키다. AI 출력이나 공개 응답 계약에 새 필드를 추가하지 않는다.
        values["result"] = {**result, _PROOF_KEY: {"input_sha256": _input_hash(source)}}


def can_reuse_truncated(
    analysis: RepoAnalysis, source: c.ShallowRepoInput, prompt_version: str
) -> bool:
    """과거 실패나 다른 입력의 partial을 성공으로 승격하거나 재사용하지 않는다."""
    if (
        analysis.analysis_level != "l1"
        or analysis.status != "partial"
        or analysis.error_code is not None
        or str(analysis.repository_id) != source.repository_id
        or analysis.head_sha != source.head_sha
        or analysis.prompt_version != prompt_version
        or not _truncation_only(source)
        or not isinstance(analysis.result, dict)
    ):
        return False
    proof = analysis.result.get(_PROOF_KEY)
    # 이전 partial에는 입력 근거가 없으므로 최신 Repository 값으로 이를 추측하지 않는다.
    return isinstance(proof, dict) and proof.get("input_sha256") == _input_hash(source)
