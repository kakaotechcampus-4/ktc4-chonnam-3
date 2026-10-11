"""공통 RepositoryCard의 필수 필드와 nullable 점수 계약을 확인한다."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.features.analysis.schemas import RepositoryCard


def test_repository_card_fields_match_openapi() -> None:
    root = Path(__file__).resolve().parents[4]
    spec = yaml.safe_load((root / "spec/shared/contracts/openapi.yaml").read_text(encoding="utf-8"))
    contract = spec["components"]["schemas"]["RepositoryCard"]
    schema = RepositoryCard.model_json_schema(by_alias=True)
    assert set(schema["required"]) == set(contract["required"])
    assert set(schema["properties"]) == set(contract["properties"])


@pytest.mark.parametrize("status", ["succeeded", "partial", "failed"])
def test_null_score_is_required_even_for_success(status: str) -> None:
    payload = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "repo",
        "fullName": "me/repo",
        "description": None,
        "languages": [],
        "topics": [],
        "stars": 0,
        "forks": 0,
        "commitCount": None,
        "userCommitCount": None,
        "pushedAt": None,
        "status": status,
        "errorCode": None,
        "recommended": False,
        "candidateSource": "rule_filter",
        "recommendReason": None,
        "matchScore": None,
        "matchedRequirementIds": [],
    }
    assert RepositoryCard.model_validate(payload).model_dump(mode="json") == payload
    del payload["matchScore"]
    with pytest.raises(ValidationError):
        RepositoryCard.model_validate(payload)
