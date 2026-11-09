"""최종 턴의 미실행 검색을 미발견·성공으로 바꾸지 않고 리포트용으로 보존한다."""

from types import SimpleNamespace

from devon_ai import contracts as c

from app.features.interview.director_service import _record_final_lookup_limitations


def test_final_lookup_preserves_previous_trace_and_explicit_unexecuted_status():
    old = {"status": "not_found", "source_ids": [], "searched_scope": [], "limitations": []}
    interview = SimpleNamespace(context_state={"external_searches": [old], "other": "kept"})
    _record_final_lookup_limitations(
        interview, (c.ExternalQueryRequest("official concept", "확인할 근거"),)
    )
    assert interview.context_state["other"] == "kept"
    assert interview.context_state["external_searches"][0] == old
    status = c.decode(c.ExternalSearchStatus, interview.context_state["external_searches"][1])
    assert status.status == "insufficient_analysis"
    assert status.source_ids == status.searched_scope == ()
    assert status.limitations == ("external_lookup_not_executed:final_turn",)


def test_no_final_query_does_not_add_a_search_result():
    interview = SimpleNamespace(context_state={"other": "kept"})
    _record_final_lookup_limitations(interview, ())
    assert interview.context_state == {"other": "kept"}
