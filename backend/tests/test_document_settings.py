import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_document_text_has_a_finite_positive_default():
    settings = Settings(_env_file=None)
    assert getattr(settings, "documents_max_text_chars", None) == 50000
    assert settings.max_upload_bytes_portfolio == 20971520


@pytest.mark.parametrize("value", [0, -1])
def test_document_text_cannot_be_unlimited(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, documents_max_text_chars=value)
