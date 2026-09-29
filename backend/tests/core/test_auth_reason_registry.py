"""OAuth와 면접 서비스가 같은 오류 레지스트리를 사용하는지 검증한다."""

import pytest

from app.core import errors
from app.core.errors import AppError
from app.shared.enums import Reason


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("invalid_state", 400),
        ("invalid_code", 400),
        ("provider_unavailable", 502),
        ("github_already_linked", 409),
        ("no_repository_selected", 400),
        ("too_many_repositories", 400),
        ("invalid_repository", 400),
        ("run_expired", 410),
        ("session_limit_exceeded", 409),
    ],
)
def test_oauth_and_interview_errors_share_registry(reason: str, status: int) -> None:
    # 면접 서비스가 공통 Reason을 넘겨도 OAuth 쪽 별도 레지스트리에서 KeyError가 나면 안 된다.
    error = AppError(Reason(reason))

    assert error.status_code == status
    envelope = error.to_envelope()["error"]
    assert envelope["reason"] == reason
    assert isinstance(envelope["message"], str) and envelope["message"]
    assert envelope["details"] == {}


def test_reason_has_one_owner_and_complete_mappings() -> None:
    assert errors.Reason is Reason
    assert set(errors.STATUS_BY_REASON) == set(Reason)
    assert set(errors.MESSAGE_BY_REASON) == set(Reason)


@pytest.mark.parametrize("display_code", ["denied", "provider_configuration"])
def test_callback_display_codes_are_not_api_reasons(display_code: str) -> None:
    with pytest.raises(ValueError):
        Reason(display_code)
