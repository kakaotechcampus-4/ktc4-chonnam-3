"""전체 목록은 고정 분석에 보존하고 세션 참조는 일정한 크기를 유지한다."""

import json

import pytest
from devon_ai import contracts as c

from app.features.interview.repository_inventory import SourceInventory, stored_inventory


def test_full_inventory_round_trip_preserves_notes_but_reference_stays_small():
    paths = tuple(f"module/source-{n}.py" for n in range(8192))
    notes = tuple(f"읽지 않은 링크: symlink-{n}" for n in range(3000))
    original = SourceInventory("a" * 40, paths, paths[:900], notes)
    restored = stored_inventory(json.loads(json.dumps(original.payload())), head_sha="a" * 40)
    assert restored == original
    reference = original.reference("repo_deep_v2")
    assert reference["path_count"] == 8192 and reference["limitation_count"] == 3000
    assert len(json.dumps(reference)) < 400
    assert "paths" not in reference and "limitations" not in reference


@pytest.mark.parametrize("damage", ["sha", "traversal", "not_observed", "type"])
def test_invalid_inventory_never_expands_the_allowed_structure(damage):
    raw = SourceInventory("a" * 40, ("src/main.py",), ("src/main.py",), ()).payload()
    if damage == "sha":
        raw["head_sha"] = "b" * 40
    elif damage == "traversal":
        raw["paths"] = ["../outside.py"]
    elif damage == "not_observed":
        raw["model_candidate_paths"] = ["unseen.py"]
    else:
        raw["limitations"] = [None]
    with pytest.raises(c.ContractError):
        stored_inventory(raw, head_sha="a" * 40)
