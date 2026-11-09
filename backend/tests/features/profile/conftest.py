"""profile_summary 테스트 공용 fixture. task-16"""

import pytest

from app.db.models import PromptVersion

from ..interview.factories import make_run, make_user


@pytest.fixture
async def prompt(db):
    db.add(
        PromptVersion(
            task_name="profile_summary",
            version="fixture-v1",
            model="fixture-model",
            template="t",
            is_active=True,
        )
    )
    await db.commit()


@pytest.fixture
async def world(db, prompt):
    user = await make_user(db)
    run = await make_run(db, user)
    await db.commit()
    return user, run
