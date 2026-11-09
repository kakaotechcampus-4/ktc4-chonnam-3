"""고정 SHA의 전체 관찰 목록을 분석 행에 한 번 보존하고 세션에는 참조만 둔다."""

import hashlib
import json
from dataclasses import asdict, dataclass

from devon_ai import contracts as c

from app.agents.director.tools import _path


@dataclass(frozen=True)
class SourceInventory:
    head_sha: str
    paths: tuple[str, ...]
    model_candidate_paths: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.head_sha) is not str
            or len(self.head_sha) != 40
            or any(character not in "0123456789abcdef" for character in self.head_sha)
            or any(
                type(values) is not tuple
                for values in (self.paths, self.model_candidate_paths, self.limitations)
            )
            or not self.paths
            or any(
                type(value) is not str
                for values in (self.paths, self.model_candidate_paths, self.limitations)
                for value in values
            )
            or len(set(self.paths)) != len(self.paths)
            or len(set(self.model_candidate_paths)) != len(self.model_candidate_paths)
            or not set(self.model_candidate_paths) <= set(self.paths)
        ):
            raise c.ContractError("semantic", "repository source inventory")
        for path in self.paths:
            _path(path)

    def payload(self) -> dict[str, object]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in asdict(self).items()
        }

    def reference(self, prompt_version: str) -> dict[str, object]:
        raw = json.dumps(self.payload(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return {
            "head_sha": self.head_sha,
            "prompt_version": prompt_version,
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "path_count": len(self.paths),
            "model_candidate_count": len(self.model_candidate_paths),
            "limitation_count": len(self.limitations),
        }


def stored_inventory(raw: object, *, head_sha: str) -> SourceInventory | None:
    if raw is None:
        return None
    if (
        type(raw) is not dict
        or set(raw) != {"head_sha", "paths", "model_candidate_paths", "limitations"}
        or raw.get("head_sha") != head_sha
        or any(
            type(raw.get(key)) is not list
            for key in ("paths", "model_candidate_paths", "limitations")
        )
        or any(
            type(value) is not str
            for key in ("paths", "model_candidate_paths", "limitations")
            for value in raw[key]
        )
    ):
        raise c.ContractError("semantic", "repository source inventory")
    return SourceInventory(
        head_sha,
        tuple(raw["paths"]),
        tuple(raw["model_candidate_paths"]),
        tuple(raw["limitations"]),
    )
