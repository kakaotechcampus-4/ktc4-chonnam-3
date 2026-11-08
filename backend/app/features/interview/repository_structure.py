"""고정 Git tree를 유한 바이트로 열거하고 완전한 부모 목록만 재사용한다."""

from typing import cast

from devon_ai import contracts as c

from app.agents.director.tools import EvidenceScope, _path
from app.core.config import Settings
from app.integrations.github.evidence import EvidenceReader, EvidenceReadError, _sha


async def recursive_files(
    reader: EvidenceReader, root: str, scope: EvidenceScope, settings: Settings, *, max_bytes: int
) -> tuple[tuple[str, ...], list[str]] | None:
    response = await reader.get(f"/git/trees/{root}?recursive=1", max_bytes=max_bytes)
    if response is None:
        return None
    entries = response.get("tree")
    if (
        response.get("sha") != root
        or type(response.get("truncated")) is not bool
        or type(entries) is not list
    ):
        raise EvidenceReadError("github_invalid_response")
    limitations: list[str] = []
    truncated = response["truncated"]
    if truncated:
        limitations.append("GitHub 재귀 구조 목록이 일부 생략되어 나머지 경로는 미확인입니다.")
    limited = len(entries) > settings.director_prepare_max_entries
    if limited:
        limitations.append("구조 항목 상한 이후의 경로는 확인하지 못했습니다.")
    observed: dict[str, dict[str, object]] = {}
    for raw in entries[: settings.director_prepare_max_entries]:
        if type(raw) is not dict:
            raise EvidenceReadError("github_invalid_response")
        path = raw.get("path")
        try:
            _path(path)
        except c.ContractError:
            raise EvidenceReadError("github_invalid_response") from None
        path = cast(str, path)
        if path in observed or type(raw.get("mode")) is not str or type(raw.get("type")) is not str:
            raise EvidenceReadError("github_invalid_response")
        _sha(raw.get("sha"))
        observed[path] = raw
    # 비재귀 응답을 재귀 목록으로 오인하지 않고 기존 경로별 순회로 돌아간다.
    if not any("/" in path for path in observed):
        return None
    complete = not truncated and not limited
    if complete:
        for path in observed:
            parent = path.rpartition("/")[0]
            if parent and (
                parent not in observed
                or observed[parent].get("type") != "tree"
                or observed[parent].get("mode") != "040000"
            ):
                raise EvidenceReadError("github_invalid_response")
        by_parent: dict[str, list[object]] = {"": []}
        for path, raw in observed.items():
            if raw.get("type") == "tree" and raw.get("mode") == "040000":
                by_parent[path] = []
        for path, raw in observed.items():
            parent = path.rpartition("/")[0]
            entry: dict[str, object] = {
                key: raw[key] for key in ("type", "mode", "sha") if key in raw
            }
            entry["path"] = path.rsplit("/", 1)[-1]
            if "size" in raw:
                entry["size"] = raw["size"]
            by_parent[parent].append(entry)

        # 같은 SHA를 다른 경로에서 만난 경우에도 동일한 tree임을 확인한다.
        def identity(values: list[object]) -> set[tuple[object, ...]]:
            return {
                tuple(item.get(key) for key in ("path", "type", "mode", "sha"))
                for item in values
                if isinstance(item, dict)
            }

        cached: dict[str, list[object]] = {}
        for path, children in by_parent.items():
            tree_sha = str(observed[path]["sha"]) if path else root
            prior = cached.get(tree_sha, reader.trees.get(tree_sha))
            if prior is not None and identity(prior) != identity(children):
                raise EvidenceReadError("github_invalid_response")
            cached[tree_sha] = children
        reader.trees.update(cached)
    files = []
    for path, raw in observed.items():
        if path.count("/") > settings.director_prepare_max_depth:
            limitations.append("구조 깊이 상한 이후의 경로는 확인하지 못했습니다.")
            continue
        if raw.get("type") == "blob" and raw.get("mode") in {"100644", "100755"}:
            files.append(path)
            size = raw.get("size")
            if type(size) is int and size >= 0:
                reader.blob_sizes[str(raw["sha"])] = size
        elif raw.get("type") != "tree" or raw.get("mode") != "040000":
            limitations.append(f"일반 파일이 아닌 항목은 읽지 않았습니다: {path}")
    return tuple(files), list(dict.fromkeys(limitations))
