"""면접 진행과 리포트가 공유하는 질문 위치·음성 HTTP 계약."""

from pathlib import Path

import yaml

from app.features.interview.schemas import InterviewTurn
from app.features.report.schemas import ReportTurn

OPENAPI = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"


def test_shared_turn_contract_matches_both_responses():
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    required = set(contract["components"]["schemas"]["InterviewTurn"]["required"])
    for model in (InterviewTurn, ReportTurn):
        assert set(model.model_json_schema(by_alias=True)["required"]) == required


def test_question_audio_contract_preserves_auth_and_text_fallback():
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert contract["security"] == [{"sessionCookie": []}]
    endpoint = contract["paths"]["/interviews/{id}/turns/{turn}/question-audio"]["get"]
    assert "security" not in endpoint
    assert endpoint["responses"]["200"]["content"]["audio/mpeg"]["schema"]["format"] == "binary"
    assert {"401", "404", "409"} <= endpoint["responses"].keys()
