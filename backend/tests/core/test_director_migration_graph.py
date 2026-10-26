"""선행 PR을 합친 실제 migration graph가 기존 이력을 모두 포함하는지 검사한다."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_migration_head_preserves_storage_analysis_and_director_history():
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    # #82·#108을 복사해 테스트를 통과시키지 않는다. 선행이 없으면 실제 graph가 실패해야 한다.
    assert len(scripts.get_heads()) == 1
    revisions = {revision.revision for revision in scripts.walk_revisions()}
    assert {
        "0001_initial",
        "0002_posting_versions",
        "0002_agent_storage",
        "0003_analysis_runs",
        "0003_director_runtime",
    } <= revisions
