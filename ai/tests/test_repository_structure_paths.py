"""구조의 디렉터리 표기와 실제 파일 근거의 경로 경계를 구분한다."""

import pytest

from devon_ai.contracts import ContractError, ShallowRepoInput, SourceDocument


def _input(path):
    return ShallowRepoInput(
        "repo", "a" * 40, None, None, False, (), None, None, (), structure=(path,)
    )


def test_structure_accepts_one_trailing_slash_for_a_directory():
    assert _input("units/submodule/").structure == ("units/submodule/",)


@pytest.mark.parametrize("path", ["units//", "/units/", "../units/", "units/../", "/"])
def test_structure_directory_marker_does_not_allow_invalid_paths(path):
    with pytest.raises(ContractError):
        _input(path)


def test_file_source_still_rejects_a_directory_marker():
    with pytest.raises(ContractError):
        SourceDocument("units/", "file", "source", "entire file")
