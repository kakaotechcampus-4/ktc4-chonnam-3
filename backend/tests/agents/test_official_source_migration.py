"""빈 DB 왕복은 허용하고 인용 가능한 공통 원문이 있으면 downgrade를 거절한다."""

import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models import InterviewExternalSource
from app.db.models.official_source import OfficialSourceSnapshot
from app.features.knowledge.official_catalog import load_catalog, prepare_snapshot
from app.features.knowledge.official_snapshots import store_snapshots
from app.integrations.search.tavily import WebSource
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


def migrate(database_url, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": database_url, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


async def test_empty_official_source_migration_can_downgrade_and_upgrade(app):
    url = app.state.settings.database_url
    down = migrate(url, "downgrade", "0013_prompt_version_capacity")
    try:
        assert down.returncode == 0, down.stderr
    finally:
        up = migrate(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr


async def test_official_source_downgrade_preserves_original_and_existing_citation(app):
    sessions = app.state.session_factory
    content = "## Task Groups\nSynthetic immutable TaskGroup passage.\n## Sleeping\nOther."
    entry = next(item for item in load_catalog() if item.catalog_key == "python-3.12-task-groups")
    draft = prepare_snapshot(
        entry,
        WebSource(
            "https://docs.python.org/3.12/library/asyncio-task.html",
            "Synthetic test original",
            content,
            "extracted_page",
            datetime.now(UTC).isoformat(),
            hashlib.sha256(content.encode()).hexdigest(),
        ),
    )
    (identifier,) = await store_snapshots(sessions, (draft,), actor="test-migration-operator")
    async with sessions.begin() as db:
        user = await make_user(db)
        run = await make_run(db, user)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo])
        citation = InterviewExternalSource(
            user_id=user.id,
            interview_session_id=interview.id,
            official_snapshot_id=identifier,
            query_text="Python TaskGroup",
            url=draft.url,
            content=draft.content,
            content_hash=draft.content_hash,
            content_scope="extracted_page",
            retrieved_at=datetime.fromisoformat(draft.retrieved_at),
            limitations=[],
        )
        db.add(citation)
        await db.flush()
        citation_id = citation.id
    result = migrate(app.state.settings.database_url, "downgrade", "0013_prompt_version_capacity")
    assert result.returncode != 0
    assert "Preserve official source snapshots and citations" in result.stderr
    async with sessions() as db:
        original = await db.get(OfficialSourceSnapshot, identifier)
        linked = await db.get(InterviewExternalSource, citation_id)
        assert (
            original.page_content == draft.page_content
            and original.content_hash == draft.content_hash
        )
        assert linked.official_snapshot_id == identifier and linked.content == draft.content
        assert await db.scalar(select(OfficialSourceSnapshot.id)) == identifier
