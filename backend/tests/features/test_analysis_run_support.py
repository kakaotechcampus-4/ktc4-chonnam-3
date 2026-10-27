"""실행 정책과 분리한 기존 인증·실패 코드·부분 성공 판정을 검증한다."""

from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.db.models.user import GithubAccount, User
from app.features.analysis.pipeline.run_support import (
    RunFailure,
    account_for_run,
    batch_outcome,
    failure_code,
)
from app.shared.enums import Reason


@pytest.mark.parametrize(
    "snapshots,expected",
    [
        ([{"status": "succeeded"}], ("succeeded", None)),
        (
            [{"status": "succeeded"}, {"status": "failed", "error_code": "rate_limited"}],
            ("partial", "rate_limited"),
        ),
        (
            [{"status": "partial", "error_code": "llm_parse_failed"}],
            ("partial", "llm_parse_failed"),
        ),
        ([{"status": "failed", "error_code": "llm_timeout"}], ("failed", "llm_timeout")),
        ([], ("failed", "llm_failed")),
    ],
)
def test_batch_outcome_keeps_partial_success(snapshots, expected):
    assert batch_outcome(snapshots) == expected


@pytest.mark.parametrize(
    "error,expected",
    [
        (AppError(Reason.GITHUB_TOKEN_INVALID), "token_invalid"),
        (AppError(Reason.UNSUPPORTED_SITE), "unsupported_site"),
        (RunFailure("jd_fetch_failed"), "jd_fetch_failed"),
        (RuntimeError("private diagnostic must not escape"), "internal_error"),
    ],
)
def test_failure_code_keeps_internal_namespace_without_exception_text(error, expected):
    assert failure_code(error) == expected


@pytest.mark.parametrize(
    "user_status,token_status,allowed",
    [("active", "valid", True), ("suspended", "valid", False), ("active", "invalid", False)],
)
async def test_account_requires_active_user_and_valid_token(
    app, db, user_status, token_status, allowed
):
    user = User(name="분석 계정 검증", status=user_status)
    db.add(user)
    await db.flush()
    account = GithubAccount(
        user_id=user.id,
        github_user_id=501,
        login="analysis-user",
        access_token_encrypted=app.state.cipher.encrypt("fixture-token"),
        token_status=token_status,
        token_scope="read:user",
    )
    db.add(account)
    await db.commit()
    ctx = {"session_factory": app.state.session_factory}
    if allowed:
        result = await account_for_run(ctx, user.id)
        assert result.id == account.id and result.login == "analysis-user"
        assert app.state.cipher.decrypt(result.access_token_encrypted) == "fixture-token"
    else:
        with pytest.raises(RunFailure) as error:
            await account_for_run(ctx, user.id)
        assert error.value.code == "token_invalid"


async def test_missing_account_is_token_invalid(app):
    with pytest.raises(RunFailure) as error:
        await account_for_run({"session_factory": app.state.session_factory}, uuid4())
    assert error.value.code == "token_invalid"
