"""과거 코호트의 출처만 해석한다. 과거 검수 상태를 현재 정답으로 올리지 않는다."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SNAPSHOT_DIRECTORY = "source_snapshot_20261108"


def is_historical_snapshot(root: Path) -> bool:
    marker = root / "provenance.json"
    return marker.is_file() and _snapshot_marker(root)["purpose"] == "binding_source_only"


def _snapshot_marker(root: Path) -> dict[str, Any]:
    # 자료 손상은 경로·파서의 내부 예외 대신 같은 검증 오류로 알린다.
    try:
        marker = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid historical source snapshot") from None
    if (
        not isinstance(marker, dict)
        or marker.get("schema_version") != "historical-eval-snapshot.v1"
        or marker.get("purpose") != "binding_source_only"
        or marker.get("current_gold") is not False
        or not isinstance(files := marker.get("files"), dict)
        or not files
        or any(
            type(relative) is not str
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for relative, digest in files.items()
        )
    ):
        raise ValueError("Invalid historical source snapshot")
    return marker


def source_file(cohort: Path, manifest: dict[str, Any], relative: str) -> Path:
    """명시한 보존 원본만 읽으며 절대 경로·상위 경로·다른 자료로의 대체는 거절한다."""
    parts = Path(relative).parts
    if parts[:2] == ("ai", "evals"):
        parts = parts[2:]
    if not parts or Path(relative).is_absolute() or ".." in parts or ":" in relative:
        raise ValueError("Invalid source provenance path")
    base = cohort.parent.resolve()
    selected = manifest.get("source_snapshot")
    if selected is not None:
        if selected != SNAPSHOT_DIRECTORY:
            raise ValueError("Unknown source snapshot")
        if parts[0] in {"inputs", "expectations"}:
            base = base / SNAPSHOT_DIRECTORY
            if not is_historical_snapshot(base):
                raise ValueError("Historical source snapshot is missing")
    target = base.joinpath(*parts).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ValueError("Source provenance file is unavailable")
    return target


def validate_bound_sources(cohort: Path) -> None:
    """코호트의 기존 지문을 보존한 채 출처의 본문·줄바꿈 정규화만 대조한다."""
    path = cohort / "binding-manifest.json"
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if "source_snapshot" not in manifest:
        return
    if manifest["source_snapshot"] != SNAPSHOT_DIRECTORY:
        raise ValueError("Unknown source snapshot")
    archive = cohort.parent / SNAPSHOT_DIRECTORY
    marker = _snapshot_marker(archive)
    for relative, expected in marker["files"].items():
        current = source_file(cohort, manifest, relative).read_bytes()
        if hashlib.sha256(current).hexdigest() != expected:
            raise ValueError("Historical source snapshot changed")
    sources = dict(manifest.get("original_files", manifest.get("source_files", {})))
    for entry in manifest.get("cases", []):
        if "source_sha256" in entry:
            sources[f"inputs/{entry['source_case']}.json"] = entry["source_sha256"]
    for relative, expected in sources.items():
        content = source_file(cohort, manifest, relative).read_text(encoding="utf-8")
        if hashlib.sha256(content.replace("\r\n", "\n").encode()).hexdigest() != expected:
            raise ValueError("Bound source fingerprint mismatch")
