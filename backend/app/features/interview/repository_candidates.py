"""실제 고정 구조의 주변 파일 경로를 원문 근거와 분리해 보존한다."""

from os.path import commonprefix

from devon_ai import contracts as c

from app.agents.director.tools import _path

STATE_KEY = "repository_lookup_candidates"
MAX_CANDIDATES = 32


def neighbor_candidates(
    observed: tuple[str, ...], selected: tuple[str, ...], *, limit: int
) -> tuple[str, ...]:
    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
        raise c.ContractError("schema", "repository candidate limit")
    for path in (*observed, *selected):
        _path(path)
    if not set(selected).issubset(observed):
        raise c.ContractError("semantic", "repository candidate selection")
    ranked: list[tuple[int, str]] = []
    for path in set(observed) - set(selected):
        parent = path.split("/")[:-1]
        distances = []
        for source in selected:
            base = source.split("/")[:-1]
            shared = len(commonprefix([parent, base]))
            distance = len(parent) + len(base) - 2 * shared
            # 같은 모듈의 가까운 디렉터리만 후보로 둔다. 루트 파일은 바로 아래까지 허용한다.
            if distance <= 2 and (shared or parent == base or not base and len(parent) <= 1):
                distances.append(distance)
        if distances:
            ranked.append((min(distances), path))
    return tuple(path for _, path in sorted(ranked)[:limit])


def snapshot_paths(raw: object, head_sha: str) -> frozenset[str]:
    """이전·손상된 snapshot은 새 조회 권한을 만들지 않고 빈 후보로 처리한다."""
    if (
        type(raw) is not dict
        or set(raw) != {"head_sha", "paths", "limitations"}
        or raw.get("head_sha") != head_sha
        or type(raw.get("paths")) is not list
        or type(raw.get("limitations")) is not list
        or any(type(value) is not str for value in raw["limitations"])
    ):
        return frozenset()
    paths = raw["paths"]
    if len(paths) > MAX_CANDIDATES or len(set(map(str, paths))) != len(paths):
        return frozenset()
    try:
        for path in paths:
            _path(path)
    except c.ContractError:
        return frozenset()
    return frozenset(paths)
