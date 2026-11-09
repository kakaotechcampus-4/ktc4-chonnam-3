"""전체 확인 구조를 버리지 않고 모델 입력 안에서 모듈별 후보를 나눈다."""

import json

import pytest
from devon_ai import contracts as c


def prepare(paths, *, limit=6000, limitations=(), enum_values=900, enum_characters=14000):
    from app.features.interview.repository_source_selection import selection_window

    shallow = c.ShallowRepoAnalysis(
        "00000000-0000-0000-0000-000000000001",
        "a" * 40,
        "서비스",
        ("처리",),
        ("backend",),
        ("Java",),
        "처리 서비스",
        (c.ShallowBasis("readme", "서비스"),),
        (),
    )
    return selection_window(
        shallow=shallow,
        prompt=c.PromptSpec("repo_deep", "v2", "fixture", "실제 경로만 선정"),
        candidates=paths,
        limitations=limitations,
        max_selected_files=8,
        max_enum_values=enum_values,
        max_enum_characters=enum_characters,
        limits=c.CallLimits(1, 2048, limit, 131072, reasoning_effort="low", stream=True),
    )


def test_window_distributes_modules_and_parent_directories_with_exact_wire_budget():
    from app.integrations.llm.client import request_size

    paths = tuple(f"north/implementation/{i}-{'long-name-' * 3}.java" for i in range(200))
    paths += tuple(f"north/verification/check-{i}.java" for i in range(20))
    paths += tuple(f"south/runtime/service-{i}.py" for i in range(100))
    paths += tuple(f"south/verification/check-{i}.py" for i in range(20)) + ("root.cfg",)
    original = tuple(paths)
    request, selected, limitations = prepare(paths)
    assert 0 < len(selected) < len(paths) and paths == original
    assert set(selected).issubset(paths) and len(set(selected)) == len(selected)
    assert {path.rpartition("/")[0] for path in selected} == {
        "north/implementation",
        "north/verification",
        "south/runtime",
        "south/verification",
        "",
    }
    assert request_size(request) <= 6000
    assert request.output_schema["properties"]["selected_paths"]["items"]["enum"] == list(selected)
    assert [row["path"] for row in request.payload["candidates"]] == list(selected)
    assert any("모델 입력 상한" in note for note in limitations)


def test_oversized_unicode_path_does_not_block_other_module_candidates():
    from app.integrations.llm.client import request_size

    paths = ("large/" + "가" * 2000 + ".src", 'small/인용"자료.src', "other/settings.cfg")
    request, selected, limitations = prepare(paths, limit=2500)
    assert paths[0] not in selected and set(selected) == set(paths[1:])
    assert request_size(request) <= 2500 and limitations
    assert (
        json.loads(json.dumps(request.payload, ensure_ascii=False))["candidates"]
        == request.payload["candidates"]
    )


def test_full_candidate_list_keeps_original_order_when_it_fits():
    paths = ("arbitrary/z.custom", "other/a.custom")
    request, selected, limitations = prepare(paths)
    assert selected == paths and limitations == ()
    assert [row["path"] for row in request.payload["candidates"]] == list(paths)


def test_request_overhead_alone_cannot_be_reported_as_a_successful_selection():
    from app.integrations.llm.client import request_size

    request, selected, limitations = prepare(("module/source.custom",), limit=100)
    assert selected == () and limitations
    assert request_size(request) > request.limits.max_input_bytes


def test_thousands_of_path_limitations_do_not_hide_regular_file_candidates():
    from app.integrations.llm.client import request_size

    original = tuple(
        f"일반 파일이 아닌 항목은 읽지 않았습니다: links/link-{i}" for i in range(3000)
    )
    request, selected, _ = prepare(("service/main.py",), limitations=original)
    assert selected == ("service/main.py",)
    assert request_size(request) <= request.limits.max_input_bytes
    assert len(request.payload["limitations"]) <= 10
    assert "3000" in " ".join(request.payload["limitations"])
    assert len(original) == 3000


@pytest.mark.parametrize("enum_values,enum_characters", [(100, 14000), (900, 500)])
def test_provider_enum_limits_apply_even_when_the_wire_request_fits(enum_values, enum_characters):
    paths = tuple(f"module-{i % 4}/source-{i:04}.py" for i in range(8192))
    request, selected, notes = prepare(
        paths, limit=1000000, enum_values=enum_values, enum_characters=enum_characters
    )
    assert 0 < len(selected) <= enum_values
    assert sum(map(len, selected)) <= enum_characters
    assert request.output_schema["properties"]["selected_paths"]["items"]["enum"] == list(selected)
    assert notes and len(paths) == 8192
