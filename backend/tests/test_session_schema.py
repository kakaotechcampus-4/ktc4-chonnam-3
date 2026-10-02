"""The accepted DB schema stores provider credentials, never login sessions."""

import importlib


def test_provider_identity_is_unique_and_session_secrets_are_not_sql_columns():
    module = importlib.import_module("app.db.models.user")
    assert hasattr(module, "GithubAccount"), "GitHub account model must be implemented"
    account = module.GithubAccount.__table__
    assert account.c.github_user_id.unique
    assert account.c.user_id.unique
    assert "access_token_encrypted" in account.c
    assert not any("refresh" in name or "expires" in name for name in account.c.keys())
    importlib.import_module("app.db.models")
    base = importlib.import_module("app.db.base").Base
    assert "auth_sessions" not in base.metadata.tables
