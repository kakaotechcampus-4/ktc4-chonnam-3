"""선행 PR을 합친 실제 migration graph가 기존 이력을 모두 포함하는지 검사한다."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import Revision, RevisionMap


def _scripts():
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    return ScriptDirectory.from_config(config)


_BASE = ("0001_initial", "0002_posting_versions")
_STORAGE = _BASE + ("0002_agent_storage", "0003_agent_storage_merge")
_ANALYSIS = _STORAGE + ("0003_analysis_runs", "0004_analysis_storage_merge")
_DIRECTOR = _ANALYSIS + (
    "0003_director_runtime",
    "0004_interview_foundation_merge",
    "0005_director_foundation_merge",
)


def test_single_migration_head_preserves_storage_analysis_and_director_history():
    scripts = _scripts()

    # #82·#108을 복사해 테스트를 통과시키지 않는다. 선행이 없으면 실제 graph가 실패해야 한다.
    assert len(scripts.get_heads()) == 1
    revisions = {revision.revision for revision in scripts.walk_revisions()}
    assert set(_DIRECTOR) <= revisions


@pytest.mark.parametrize(
    ("included", "expected_head"),
    [
        (_BASE, "0002_posting_versions"),
        (_STORAGE, "0003_agent_storage_merge"),
        (_ANALYSIS, "0004_analysis_storage_merge"),
        (_DIRECTOR, "0005_director_foundation_merge"),
    ],
    ids=["develop", "storage", "analysis", "director"],
)
def test_each_published_snapshot_has_one_head_without_losing_history(included, expected_head):
    # 실제 선행 Script에서 읽은 ID·부모만 사용한다. 없는 선행을 가짜 revision으로 보충하지 않는다.
    actual = {revision.revision: revision for revision in _scripts().walk_revisions()}
    snapshot = []
    for revision_id in included:
        revision = actual[revision_id]
        snapshot.append(
            Revision(
                revision.revision,
                revision.down_revision,
                dependencies=revision.dependencies,
                branch_labels=revision.branch_labels,
            )
        )
    assert RevisionMap(lambda: iter(snapshot)).heads == (expected_head,)
