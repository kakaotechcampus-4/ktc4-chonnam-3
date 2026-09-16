import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_auth_migration_roundtrip_and_constraints():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set isolated TEST_DATABASE_URL for PostgreSQL migration test")
    assert url.endswith("/devon_oauth_test")
    engine = create_async_engine(url)
    config = Config("alembic.ini")
    async with engine.begin() as connection:

        def migrate(sync_connection):
            from app.db.base import Base

            config.attributes["connection"] = sync_connection
            command.upgrade(config, "0001")
            user_id, account_id = uuid4(), uuid4()
            sync_connection.execute(
                text(
                    "INSERT INTO users (id, display_name, last_login_at) "
                    "VALUES (:id, 'Existing User', now())"
                ),
                {"id": user_id},
            )
            sync_connection.execute(
                text(
                    "INSERT INTO github_accounts "
                    "(id, user_id, github_user_id, login, access_token_encrypted, token_scope) "
                    "VALUES (:id, :user_id, 9876, 'existing', :token, 'read:user')"
                ),
                {"id": account_id, "user_id": user_id, "token": b"existing-ciphertext"},
            )
            command.upgrade(config, "head")
            inspector = inspect(sync_connection)
            assert {"users", "github_accounts", "auth_sessions"} <= set(inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("github_accounts")}
            assert "access_token_encrypted" in columns
            assert not {"refresh_token_encrypted", "token_expires_at", "token_type"} & columns
            assert len(inspector.get_unique_constraints("github_accounts")) == 2
            assert len(inspector.get_check_constraints("users")) == 1
            generation = sync_connection.scalar(
                text("SELECT refresh_generation FROM users WHERE id = :id"), {"id": user_id}
            )
            assert generation is not None
            assert (
                sync_connection.scalar(
                    text("SELECT access_token_encrypted FROM github_accounts WHERE id = :id"),
                    {"id": account_id},
                )
                == b"existing-ciphertext"
            )
            assert {
                index["column_names"][0] for index in inspector.get_indexes("auth_sessions")
            } == {"user_id", "expires_at"}
            assert (
                inspector.get_foreign_keys("auth_sessions")[0]["options"]["ondelete"] == "CASCADE"
            )
            assert (
                compare_metadata(MigrationContext.configure(sync_connection), Base.metadata) == []
            )
            command.downgrade(config, "0001")
            assert "auth_sessions" not in inspect(sync_connection).get_table_names()
            assert sync_connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert sync_connection.scalar(text("SELECT count(*) FROM github_accounts")) == 1
            command.upgrade(config, "head")
            assert (
                sync_connection.scalar(
                    text("SELECT refresh_generation FROM users WHERE id = :id"), {"id": user_id}
                )
                != generation
            )
            command.downgrade(config, "base")
            assert "users" not in inspect(sync_connection).get_table_names()

        await connection.run_sync(migrate)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()
