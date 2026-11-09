"""큰 텍스트를 원문 줄 위치와 유한 예산을 유지해 분리한다."""


def test_large_source_segments_keep_exact_lines_overlap_and_total_budget():
    from app.features.interview.source_segments import segment_text

    text = "".join(f"line-{number:02d}\n" for number in range(1, 13))
    sources, limitations = segment_text(
        "module/arbitrary.src", text, max_segment_bytes=32, total_bytes=128, overlap_lines=1
    )
    assert len(sources) > 1
    assert sources[0].start_line == 1
    assert sources[1].start_line == sources[0].end_line
    for source in sources:
        assert source.end_line is not None
        assert source.content == "".join(
            text.splitlines(keepends=True)[source.start_line - 1 : source.end_line]
        )
        assert len(source.content.encode()) <= 32
        assert source.read_scope == f"lines {source.start_line}-{source.end_line}"
    assert sum(len(source.content.encode()) for source in sources) <= 128
    assert sources[-1].end_line == 12
    assert not limitations


def test_budget_exhaustion_preserves_partial_source_and_unread_line_range():
    from app.features.interview.source_segments import segment_text

    sources, limitations = segment_text(
        "nested/unknown.ext", "one\ntwo\nthree\nfour\n", max_segment_bytes=8, total_bytes=8
    )
    assert sources[0].content == "one\ntwo\n"
    assert sources[0].start_line == 1 and sources[0].end_line == 2
    assert any("3-4" in note for note in limitations)


def test_overlong_line_is_not_sliced_into_a_falsely_complete_line():
    from app.features.interview.source_segments import segment_text

    sources, limitations = segment_text(
        "data.cfg", "x" * 30 + "\nvalid\n", max_segment_bytes=10, total_bytes=20
    )
    assert len(sources) == 1
    assert sources[0].content == "valid\n"
    assert sources[0].start_line == sources[0].end_line == 2
    assert any("1" in note for note in limitations)


def test_cached_scopes_reuse_exact_ranges_instead_of_resegmenting_a_file():
    from app.features.interview.repository_sources import _cached_segments

    text = "one\ntwo\nthree\nfour\nfive\n"
    sources, limitations = _cached_segments(
        "module/x.src",
        text,
        (("module/x.src", "lines 2-3"), ("module/x.src", "lines 4-5")),
        100,
        100,
    )
    assert [(source.start_line, source.end_line) for source in sources] == [(2, 3), (4, 5)]
    assert [source.content for source in sources] == ["two\nthree\n", "four\nfive\n"]
    assert not limitations
