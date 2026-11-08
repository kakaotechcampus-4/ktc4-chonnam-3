"""조회 상한의 0·무한대·잘못된 타입이 실제 실행 설정을 통과하지 못한다."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "field,value",
    [
        ("director_evidence_max_total_bytes", True),
        ("director_prepare_max_entries", 0),
        ("director_prepare_max_depth", -1),
    ],
)
def test_invalid_director_read_budget_is_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
