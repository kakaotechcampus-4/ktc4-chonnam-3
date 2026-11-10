"""조회 상한의 0·무한대·잘못된 타입이 실제 실행 설정을 통과하지 못한다."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "field,value",
    [
        ("director_evidence_max_total_bytes", True),
        ("director_prepare_max_response_bytes", True),
        ("director_prepare_max_total_bytes", 0),
        ("director_prepare_max_source_bytes", -1),
        ("director_prepare_max_entries", 0),
        ("director_prepare_max_depth", -1),
        ("repository_selection_max_enum_values", 0),
        ("repository_selection_max_enum_values", True),
        ("repository_selection_max_enum_characters", -1),
        ("repository_selection_max_enum_characters", 1.5),
    ],
)
def test_invalid_director_read_budget_is_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_repository_selection_schema_limits_can_follow_the_selected_provider():
    settings = Settings(
        _env_file=None,
        repository_selection_max_enum_values=400,
        repository_selection_max_enum_characters=8000,
    )
    assert settings.repository_selection_max_enum_values == 400
    assert settings.repository_selection_max_enum_characters == 8000
