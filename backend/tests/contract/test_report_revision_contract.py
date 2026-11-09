"""REST 원본과 WS 확장 문서가 실제 오류·중복 단위를 잃지 않는지 검사한다."""

from pathlib import Path

import yaml

from app.features.interview.schemas import InterviewTurn
from app.features.report.schemas import ReportTurn
from app.shared.enums import AnswerMode

ROOT = Path(__file__).resolve().parents[3]


def test_active_turn_shapes_and_answer_modes_match_the_shared_contract():
    contract = yaml.safe_load(
        (ROOT / "spec/shared/contracts/openapi.yaml").read_text(encoding="utf-8")
    )["components"]["schemas"]
    expected = set(contract["InterviewTurn"]["required"])
    # 선행 음성 확장을 적용할 때도 공통 계약과 두 실제 응답이 함께 바뀌어야 한다.
    for model in (InterviewTurn, ReportTurn):
        assert {field.alias or name for name, field in model.model_fields.items()} == expected
    assert set(contract["AnswerMode"]["enum"]) == {mode.value for mode in AnswerMode}


def test_report_submission_documents_the_current_reason_and_revision_unit():
    contract = yaml.safe_load(
        (ROOT / "spec/shared/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    operation = contract["paths"]["/interviews/{id}/feedback-disagreements"]["post"]
    conflict = operation["responses"]["409"]
    assert conflict["content"]["application/json"]["schema"]["$ref"].endswith("/ApiError")
    assert "report_unavailable" in conflict["description"]
    assert "already_submitted" in conflict["description"]
    assert "(interviewId, revision, persona)" in operation["description"]


def test_ws_error_details_are_optional_not_a_new_reason_or_required_payload():
    document = (ROOT / "frontend/docs/api-spec.md").read_text(encoding="utf-8")
    row = next(
        line
        for line in document.splitlines()
        if line.startswith("| `error` |") and "`recoverable`" in line
    )
    assert "`details`" in row and "선택" in row
    assert "empty_transcript" in document
