import pytest

from devon_ai import contracts as c

SHA = "a" * 40


def _input(repository_id: str = "repo-1") -> c.ShallowRepoInput:
    return c.ShallowRepoInput(
        repository_id=repository_id,
        head_sha=SHA,
        description="cache service",
        readme_text="A cache service",
        readme_truncated=False,
        languages=(c.LanguageBytes("Python", 120),),
        commit_count=10,
        user_commit_count=3,
        collection_errors=(),
    )


def _shallow(repository_id: str = "repo-1", head_sha: str = SHA) -> c.ShallowRepoAnalysis:
    return c.ShallowRepoAnalysis(
        repository_id=repository_id,
        head_sha=head_sha,
        purpose="캐시 서비스",
        key_features=("캐시 조회",),
        project_types=("backend",),
        tech_stack=("Python",),
        project_role_summary="캐시 기능을 제공하는 프로젝트",
        basis=(c.ShallowBasis("readme", "캐시 서비스를 제공함"),),
        limitations=("실행 동작 미확인",),
    )


def test_shallow_batch_matches_by_id_even_when_results_are_reordered() -> None:
    result = c.validate_shallow_batch(
        (_input("repo-1"), _input("repo-2")),
        (_shallow("repo-2"), _shallow("repo-1")),
    )
    assert [item.repository_id for item in result.data.succeeded] == ["repo-1", "repo-2"]
    assert result.data.failed == ()


def test_shallow_batch_preserves_valid_item_and_reports_missing_unknown_duplicate_and_stale() -> (
    None
):
    result = c.validate_shallow_batch(
        (_input("valid"), _input("duplicate"), _input("missing"), _input("stale")),
        (
            _shallow("valid"),
            _shallow("duplicate"),
            _shallow("duplicate"),
            _shallow("unknown"),
            _shallow("stale", "b" * 40),
        ),
    ).data
    assert tuple(item.repository_id for item in result.succeeded) == ("valid",)
    assert {item.repository_id for item in result.failed} == {
        "duplicate",
        "missing",
        "stale",
        "unknown",
    }
    assert all(item.stage == "semantic" for item in result.failed)


def test_parse_shallow_batch_keeps_valid_sibling_when_one_item_has_bad_schema() -> None:
    valid = {
        "repository_id": "valid",
        "head_sha": SHA,
        "purpose": "캐시 서비스",
        "key_features": ["조회"],
        "project_types": ["backend"],
        "tech_stack": ["Python"],
        "project_role_summary": "캐시 기능 제공",
        "basis": [{"kind": "readme", "claim": "캐시 서비스"}],
        "limitations": [],
    }
    invalid = {**valid, "repository_id": "invalid", "tech_stack": None}

    result = c.parse_shallow_batch([valid, invalid], inputs=(_input("valid"), _input("invalid")))

    assert tuple(item.repository_id for item in result.data.succeeded) == ("valid",)
    schema_failures = [item for item in result.data.failed if item.stage == "schema"]
    assert len(schema_failures) == 1
    assert schema_failures[0].repository_id == "invalid"


def test_parse_shallow_batch_preserves_unidentifiable_schema_failure_without_fake_id() -> None:
    result = c.parse_shallow_batch(
        [{"head_sha": SHA, "purpose": "missing id"}], inputs=(_input("missing"),)
    ).data
    assert any(item.repository_id is None and item.stage == "schema" for item in result.failed)
    assert any(
        item.repository_id == "missing" and item.stage == "semantic" for item in result.failed
    )


def test_parse_shallow_batch_rejects_mixed_valid_and_invalid_duplicate_without_success() -> None:
    valid = {
        "repository_id": "repo-1",
        "head_sha": SHA,
        "purpose": "캐시 서비스",
        "key_features": ["조회"],
        "project_types": ["backend"],
        "tech_stack": ["Python"],
        "project_role_summary": "캐시 기능 제공",
        "basis": [{"kind": "readme", "claim": "캐시 서비스"}],
        "limitations": [],
    }
    malformed = {**valid, "tech_stack": None}
    result = c.parse_shallow_batch([valid, malformed], inputs=(_input(),)).data
    assert result.succeeded == ()
    assert [(item.repository_id, item.stage) for item in result.failed] == [("repo-1", "semantic")]


def test_parse_shallow_batch_preserves_semantic_stage_from_candidate_validation() -> None:
    raw = {
        "repository_id": "repo-1",
        "head_sha": SHA,
        "purpose": "캐시 서비스",
        "key_features": ["조회", "조회"],
        "project_types": ["backend"],
        "tech_stack": ["Python"],
        "project_role_summary": "캐시 기능 제공",
        "basis": [{"kind": "readme", "claim": "캐시 서비스"}],
        "limitations": [],
    }
    result = c.parse_shallow_batch([raw], inputs=(_input(),)).data
    assert result.succeeded == ()
    assert result.failed[0].stage == "semantic"


@pytest.mark.parametrize("head_sha", [None, 42])
def test_parse_shallow_batch_missing_or_wrong_type_sha_is_schema_failure(head_sha) -> None:
    raw = {"repository_id": "repo-1"}
    if head_sha is not None:
        raw["head_sha"] = head_sha
    result = c.parse_shallow_batch([raw], inputs=(_input(),)).data
    assert len(result.failed) == 1
    assert result.failed[0].stage == "schema"


@pytest.mark.parametrize("head_sha", ["main", "a" * 39, "g" * 40, "A" * 40])
def test_repository_contract_requires_lowercase_full_sha(head_sha: str) -> None:
    with pytest.raises(c.ContractError):
        _shallow(head_sha=head_sha)


def test_partial_l0_input_requires_l1_limitations() -> None:
    source = c.ShallowRepoInput("repo-1", SHA, None, None, False, (), None, None, ("no_readme",))
    candidate = c.ShallowRepoAnalysis(
        "repo-1",
        SHA,
        "미확인",
        (),
        (),
        (),
        "확인 자료 부족",
        (c.ShallowBasis("description", "설명 없음"),),
        (),
    )
    result = c.validate_shallow_batch((source,), (candidate,)).data
    assert result.succeeded == ()
    assert result.failed[0].repository_id == "repo-1"
    assert result.failed[0].stage == "semantic"


def test_truncated_readme_requires_limitation_and_basis_must_exist_in_input() -> None:
    truncated = c.ShallowRepoInput("repo-1", SHA, None, "partial readme", True, (), None, None, ())
    original = _shallow()
    no_limitation = c.ShallowRepoAnalysis(
        original.repository_id,
        original.head_sha,
        original.purpose,
        original.key_features,
        original.project_types,
        original.tech_stack,
        original.project_role_summary,
        original.basis,
        (),
    )
    assert c.validate_shallow_batch((truncated,), (no_limitation,)).data.failed

    no_readme = c.ShallowRepoInput("repo-1", SHA, None, None, False, (), None, None, ())
    readme_claim = _shallow()
    result = c.validate_shallow_batch((no_readme,), (readme_claim,)).data
    assert result.succeeded == ()
    assert result.failed[0].stage == "semantic"


def _deep_input() -> c.DeepRepoInput:
    return c.DeepRepoInput(
        "repo-1",
        SHA,
        _shallow(),
        (
            c.SourceDocument("src/cache.py", "file", "class Cache: pass", "entire file"),
            c.SourceDocument("src/services", "directory", "cache.py\napi.py", "one-level listing"),
        ),
    )


def _deep(**changes: object) -> c.DeepRepoAnalysis:
    values: dict[str, object] = {
        "repository_id": "repo-1",
        "head_sha": SHA,
        "architecture_summary": "캐시 서비스 계층이 있음",
        "confirmed_technologies": ("Python",),
        "notable_areas": (c.NotableArea("src/cache.py", "캐시 클래스", "entire file", ()),),
        "limitations": ("실행 결과 미확인",),
    }
    values.update(changes)
    return c.DeepRepoAnalysis(**values)  # type: ignore[arg-type]


def test_deep_analysis_accepts_only_registered_path_and_exact_read_scope() -> None:
    checked = c.validate_deep_analysis(_deep(), source=_deep_input())
    assert checked.data.notable_areas[0].path == "src/cache.py"

    with pytest.raises(c.ContractError):
        c.validate_deep_analysis(
            _deep(
                notable_areas=(c.NotableArea("src/cache.py", "캐시 클래스", "selected lines", ()),)
            ),
            source=_deep_input(),
        )


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "src\\cache.py", "src/./cache.py"])
def test_repository_paths_reject_traversal_absolute_and_non_github_forms(path: str) -> None:
    with pytest.raises(c.ContractError):
        c.SourceDocument(path, "file", "content", "entire file")


def test_deep_analysis_rejects_stale_sha_unknown_path_duplicates_and_area_count() -> None:
    source = _deep_input()
    invalid = (
        _deep(head_sha="b" * 40),
        _deep(notable_areas=(c.NotableArea("unknown.py", "x", "entire file", ()),)),
        _deep(
            notable_areas=(
                c.NotableArea("src/cache.py", "x", "entire file", ()),
                c.NotableArea("src/cache.py", "y", "entire file", ()),
            )
        ),
        _deep(notable_areas=()),
        _deep(
            notable_areas=tuple(
                c.NotableArea("src/cache.py", str(index), "entire file", ()) for index in range(6)
            )
        ),
    )
    for candidate in invalid:
        with pytest.raises(c.ContractError) as failure:
            c.validate_deep_analysis(candidate, source=source)
        assert failure.value.stage == "semantic"


def test_checked_repository_result_serializes_without_raw_candidate_access() -> None:
    result = c.validate_shallow_batch((_input(),), (_shallow(),))
    data = c.to_data(result)
    assert data["succeeded"][0]["repository_id"] == "repo-1"  # type: ignore[index]
    with pytest.raises(c.ContractError):
        c.to_data(_shallow())  # type: ignore[arg-type]
