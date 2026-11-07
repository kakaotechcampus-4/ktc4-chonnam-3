"""진행 중 근거 조회가 무제한·잘못된 상한으로 설정되지 않는지 검사한다."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "field,value",
    [
        ("director_evidence_max_files", 0),
        ("director_evidence_max_requests", -1),
        ("director_evidence_timeout_seconds", float("inf")),
    ],
)
def test_invalid_director_runtime_read_budget_is_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
