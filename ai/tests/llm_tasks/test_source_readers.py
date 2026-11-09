"""전용 읽기는 보조 정보이고 지원 밖 형식도 원문 구간으로 유지한다."""

from devon_ai import contracts as c


def test_json_toml_and_python_readers_only_describe_supplied_source():
    from devon_ai.source_readers import describe_source

    assert (
        describe_source(c.SourceDocument("x.json", "file", '{"app": 1}', "entire file"))["reader"]
        == "json"
    )
    assert (
        describe_source(c.SourceDocument("x.toml", "file", "[tool]\nvalue = 1\n", "entire file"))[
            "reader"
        ]
        == "toml"
    )
    result = describe_source(
        c.SourceDocument("other/module.py", "file", "def work():\n    return 1\n", "entire file")
    )
    assert result["symbols"] == [
        {"kind": "function", "name": "work", "start_line": 1, "end_line": 2}
    ]


def test_unsupported_or_incomplete_source_uses_explicit_raw_fallback():
    from devon_ai.source_readers import describe_source

    for source in (
        c.SourceDocument("module/new.lang", "file", "whatever", "entire file"),
        c.SourceDocument("x.json", "file", '{"app":', "entire file"),
        c.SourceDocument("x.toml", "file", "part = 1\n", "lines 5-5", 5, 5),
    ):
        result = describe_source(source)
        assert result["reader"] == "raw_text"
        assert result["limitations"]
