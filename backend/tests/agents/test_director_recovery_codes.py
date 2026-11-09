"""Director 후보 복구 오류코드는 알려진 실패로만 분류되고 실행·대체로 이어지지 않는다."""

import pytest
from devon_ai import contracts as c
from devon_ai.agents.director.agent import candidate_recovery
from structlog.testing import capture_logs

from app.core.errors import DIRECTOR_CANDIDATE_RECOVERY_CODES
from app.features.interview.director_service import log_recovery, recovery_code

CODES = {"director_candidate_rewrite", "director_candidate_replan", "director_no_valid_candidate"}


def failure(code: str) -> c.CallFailure:
    return c.CallFailure("semantic", code, "Independent question review rejected.")


def test_registered_codes_match_the_codes_ai_can_restore():
    assert DIRECTOR_CANDIDATE_RECOVERY_CODES == CODES
    assert all(candidate_recovery(failure(code)) is not None for code in CODES)


@pytest.mark.parametrize("code", sorted(DIRECTOR_CANDIDATE_RECOVERY_CODES))
def test_known_recovery_code_is_classified(code):
    assert recovery_code(failure(code)) == code


@pytest.mark.parametrize(
    "item",
    [
        None,
        failure("director_review_failed"),
        failure("director_candidate_invalid"),
        failure("director_review_timeout"),
        failure("unknown_future_code"),
    ],
)
def test_other_failures_keep_the_existing_path(item):
    assert recovery_code(item) is None
    with capture_logs() as logs:
        log_recovery(item, "turn")
    assert logs == []


def test_recovery_log_carries_phase_and_code_but_no_raw_text():
    with capture_logs() as logs:
        log_recovery(failure("director_candidate_replan"), "prepare")
    assert logs == [
        dict(
            event="director_candidate_recovery_blocked",
            log_level="warning",
            phase="prepare",
            error_code="director_candidate_replan",
        )
    ]
