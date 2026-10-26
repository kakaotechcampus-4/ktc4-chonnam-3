"""실제 revision graph가 공고 버전과 Agent 저장 가지를 함께 포함하는지 검사한다."""

from pathlib import Path

from alembic.script import ScriptDirectory


def test_agent_and_posting_storage_are_reachable_from_one_migration_head():
    script = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "migrations"))

    assert len(script.get_heads()) == 1
    revisions = {revision.revision for revision in script.walk_revisions()}
    assert {"0002_agent_storage", "0002_posting_versions"} <= revisions
