"""저장 경계와 분석 실행을 순서대로 반영해도 하나의 전진 지점으로 합친다."""

from pathlib import Path

from alembic.script import ScriptDirectory


def test_analysis_and_storage_branches_have_one_shared_head():
    script = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations"))
    assert len(script.get_heads()) == 1
    applied = {revision.revision for revision in script.walk_revisions()}
    assert {
        "0002_agent_storage",
        "0002_posting_versions",
        "0003_agent_storage_merge",
        "0003_analysis_runs",
    } <= applied
