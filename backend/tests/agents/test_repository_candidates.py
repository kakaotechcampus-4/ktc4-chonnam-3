"""추가 조회 후보는 실제 고정 구조의 가까운 일반 파일로 제한한다."""

from importlib import import_module, util

import pytest
from devon_ai import contracts as c


def helper():
    name = "app.features.interview.repository_candidates"
    assert util.find_spec(name), "고정 구조 후보를 보존하고 검증하는 경계가 필요합니다."
    return import_module(name)


def test_neighbors_are_bounded_actual_paths_without_required_filenames():
    value = helper().neighbor_candidates(
        ("module/run.rb", "module/config/custom.conf", "module/test/check.rb", "other/main.go"),
        ("module/run.rb",),
        limit=2,
    )
    assert value == ("module/config/custom.conf", "module/test/check.rb")


def test_candidates_are_deterministic_and_do_not_include_selected_files():
    paths = ("a/x.custom", "a/z.other", "a/entry", "a/y.txt")
    assert helper().neighbor_candidates(paths, ("a/entry",), limit=2) == ("a/x.custom", "a/y.txt")
    assert helper().neighbor_candidates(tuple(reversed(paths)), ("a/entry",), limit=2) == (
        "a/x.custom",
        "a/y.txt",
    )


def test_snapshot_is_bound_to_sha_and_invalid_paths_are_not_authorized():
    api = helper()
    snapshot = {"head_sha": "a" * 40, "paths": ["a/x.py"], "limitations": ["부분 구조"]}
    assert api.snapshot_paths(snapshot, "a" * 40) == frozenset({"a/x.py"})
    assert api.snapshot_paths(snapshot, "b" * 40) == frozenset()
    assert api.snapshot_paths({**snapshot, "paths": ["../outside.py"]}, "a" * 40) == frozenset()
    assert api.snapshot_paths({**snapshot, "paths": ["a/x.py"] * 2}, "a" * 40) == frozenset()


def test_invalid_limits_and_unobserved_selection_are_rejected():
    for limit in (0, -1, True):
        with pytest.raises(c.ContractError):
            helper().neighbor_candidates(("a/x.py",), (), limit=limit)
    with pytest.raises(c.ContractError):
        helper().neighbor_candidates(("a/x.py",), ("a/invented.py",), limit=2)
