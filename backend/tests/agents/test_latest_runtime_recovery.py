"""실제 최신 정책·PG에 모의 HTTP만 결합해 복구 연결을 검증한다. 모델 품질 평가는 아니다."""

import copy
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import httpx
import pytest
from devon_ai import contracts as c
from devon_ai.agents.director.runtime import operation_prompts
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, PromptVersion
from app.features.interview.answer_context import load_answer_context, prior_analyses
from app.features.interview.director_service import process_answer
from app.features.report.history import enrich_report_history
from tests.agents.director_helpers import approved_review, response, seed_turns, settings

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai/evals"))

from async_grader import content_hash  # noqa: E402
from director_diagnostics import validate_diagnostics  # noqa: E402

from scripts.ai_eval_bridge import _attempts  # noqa: E402

DIRECTOR = "director_v17@calibrated-review"
ANALYSIS = "answer_analysis_v7@claim-contribution-scope"
ANSWER = "팀원 담당입니다"
PROMPTS = {
    "director": (DIRECTOR, "director-runtime-v17-calibrated-review.md"),
    "answer_analysis": (ANALYSIS, "answer-analysis-runtime-v7-claim-contribution-scope.md"),
}


def wire_analysis():
    return {
        "coverage_assessment": {
            "evaluation_status": "evaluated",
            "sufficiency": "sufficient",
            "covered_points": {"role": ["answer:0001"]},
            "missing_points": [],
            "limitations": [],
        },
        "technical_assessment": {
            "explanation": "역할만 확인하고 코드 구현은 확인하지 않았다.",
            "quote_ids": [],
            "evidence_refs": [],
            "limitations": ["구현 원문 미확인"],
        },
        "contribution_scope": {
            "scope": "teammate",
            "quote_ids": ["answer:0001"],
            "unknown_reason": None,
        },
        "claim_checks": [
            {
                "quote_id": "answer:0001",
                "claim_excerpt": "팀원 담당",
                "status": "unverified",
                "evidence_refs": [],
                "limitations": ["개인 구현 원문 미확인"],
            }
        ],
        "verification_requests": [],
        "external_queries": [],
    }


def round_diagnostics(sent, record, recovery):
    """실제 HTTP 본문과 DB 원시 시도를 라운드별로 결합한다."""
    summaries = _attempts([c.AttemptMetadata(**row) for row in record.attempts])
    input_hash = content_hash(sent[0]["payload"])
    requests = []
    for observed, attempt in zip(sent, record.attempts, strict=True):
        body, payload = observed["body"], observed["payload"]
        requests.append(
            {
                "operation": payload["operation"],
                "prompt_version": attempt["prompt_version"],
                "prompt_template": body["instructions"],
                "prompt_template_sha256": hashlib.sha256(body["instructions"].encode()).hexdigest(),
                "model": body["model"],
                "schema_version": attempt["schema_version"],
                "payload": payload,
                "payload_sha256": content_hash(payload),
            }
        )
    snapshot = {
        "schema_version": "director-model-sources.v3",
        "service_input_sha256": input_hash,
        "requests": requests,
    }
    reviewed = record.attempts[1]
    diagnostic = {
        "schema_version": "director-diagnostics.v2",
        "service_input_sha256": input_hash,
        "source_snapshot_sha256": content_hash(snapshot),
        "reviews": [
            {
                "request_index": 1,
                "attempt_index": 1,
                "request_payload_sha256": requests[1]["payload_sha256"],
                "prompt_version": reviewed["prompt_version"],
                "prompt_template_sha256": requests[1]["prompt_template_sha256"],
                "response_raw_sha256": hashlib.sha256(reviewed["raw_output"].encode()).hexdigest(),
                "response_model": reviewed["model"],
                "assessment": json.loads(reviewed["raw_output"]),
                "recovery": recovery,
            }
        ],
    }
    assert (
        validate_diagnostics(
            diagnostic,
            service_input_sha256=input_hash,
            source_snapshot=snapshot,
            attempts=summaries,
        )
        == diagnostic
    )
    return snapshot, diagnostic, summaries


@pytest.mark.parametrize("kind", ["rewrite", "replan"])
async def test_latest_policies_restore_v7_and_recover_once_without_rewriting_audit(
    agent_sessions, agent_seed, kind
):
    await seed_turns(agent_sessions, agent_seed)
    specs = {}
    async with agent_sessions.begin() as db:
        for task, (version, filename) in PROMPTS.items():
            row = await db.scalar(select(PromptVersion).where(PromptVersion.task_name == task))
            row.version = version
            row.template = (ROOT / "ai/prompts" / filename).read_text(encoding="utf-8")
            row.model = "fixture-model"
            specs[task] = c.PromptSpec(task, version, row.model, row.template)
    expected_prompts = operation_prompts(specs["director"])
    sent, plans, first_analysis, failed_audit = [], [], [], []
    call_id = uuid4()
    raw_t3 = wire_analysis()

    async def handle(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        sent.append({"body": body, "payload": payload})
        assert body["model"] == "fixture-model"
        if body["text"]["format"]["name"] == "AnswerAnalysis":
            assert body["instructions"] == specs["answer_analysis"].template
            assert "claim_excerpt" in json.dumps(body["text"]["format"]["schema"])
            return response(raw_t3)
        operation = payload["operation"]
        assert body["instructions"] == expected_prompts[int(operation == "review")].template
        if operation == "plan":
            async with agent_sessions() as db:
                turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
                if not first_analysis:
                    first_analysis.append(copy.deepcopy(turn.analysis))
                assert turn.answer_text == ANSWER and turn.analysis == first_analysis[0]
                if plans:
                    original = await db.get(LLMCallRecord, uuid5(call_id, "director"))
                    failed_audit.append(copy.deepcopy(original.attempts))
            keys = next(
                (
                    row["keys"]
                    for row in payload["context"]["evaluation_targets"]
                    if row["persona"] == "tech_lead"
                ),
                [],
            )
            question = {
                "persona": "tech_lead",
                "preamble": "",
                "request": "본인의 역할을 설명해 주세요."
                if not plans
                else "팀과 본인의 역할을 구분해 주세요.",
                "topic_code": "role",
                "question_contract": {
                    "point_key": "role",
                    "assumptions": [],
                    "basis_refs": [],
                    "evaluation_keys": keys,
                },
                "evidence_refs": [],
                "jd_requirement_ids": [],
                "question_type": "main",
                "parent_turn_id": None,
            }
            plans.append(question)
            return response(
                {"question": question, "intent": "역할 확인", "reason_summary": "허용 범위"}
            )
        review = approved_review()
        if len(plans) == 1:
            review["wording_valid" if kind == "rewrite" else "plan_valid"] = False
        review["point_coverage"] = [
            {
                "key": "role",
                "status": "asked",
                "question_excerpt": payload["question"]["question_contract"]["required_points"][0][
                    "description"
                ],
            }
        ]
        return response(review)

    arguments = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=1,
        text=ANSWER,
        call_id=call_id,
        settings=settings(),
    )
    # 외부 모델 호출은 전부 MockTransport가 담당하며 DB·서비스·decoder는 실제 코드다.
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(agent_sessions, **arguments, http_client=http)
        assert result.failure is None and result.next_turn_id is not None
        assert len(sent) == 5
        replay = await process_answer(agent_sessions, **arguments, http_client=http)
        assert replay.next_turn_id == result.next_turn_id and len(sent) == 5

    assert [row["payload"].get("operation", "analysis") for row in sent] == [
        "analysis",
        "plan",
        "review",
        "plan",
        "review",
    ]
    assert sent[3]["payload"]["recovery_feedback"]["recovery"] == kind
    assert all("recovery_feedback" not in sent[index]["payload"] for index in (1, 2, 4))
    assert all(row["payload"]["answer_analysis"] == first_analysis[0] for row in sent[1:])
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert len(turns) == 2 and interview.current_turn == 2
        original_turn, recovered_turn = turns
        assert recovered_turn.id == result.next_turn_id
        assert original_turn.answer_text == ANSWER and original_turn.analysis == first_analysis[0]
        assert original_turn.analysis["claim_checks"][0]["claim_text"] == "팀원 담당"
        assert original_turn.analysis["contribution_scope"] == {
            "scope": "teammate",
            "answer_quotes": [ANSWER],
        }
        assert (
            recovered_turn.question_text
            == recovered_turn.question_contract["purpose"]
            == plans[1]["request"]
        )
        original = await db.get(LLMCallRecord, uuid5(call_id, "director"))
        assert original.turn_id is None
        assert original.failure["error_code"] == "director_candidate_" + kind
        assert original.attempts == failed_audit[0]
        assert json.loads(original.attempts[0]["raw_output"])["question"] == plans[0]
        (entry,) = interview.context_state["question_retry_v1"].values()
        assert entry["kind"] == "auto" and entry["recovery_kind"] == kind
        assert entry["status"] == "succeeded"
        assert entry["failed_call_id"] == str(original.id) and len(entry["failure_binding"]) == 64
        recovered = await db.get(LLMCallRecord, UUID(entry["call_id"]))
        assert recovered.turn_id == recovered_turn.id and recovered.failure is None
        for record in (original, recovered):
            assert [row["schema_version"] for row in record.attempts] == [
                "director-plan.v4",
                "director-review.v3",
            ]
            assert {row["prompt_version"] for row in record.attempts} == {DIRECTOR}
        t3 = await db.get(LLMCallRecord, call_id)
        assert len(t3.attempts) == 1 and t3.attempts[0]["schema_version"] == "7"
        assert t3.attempts[0]["prompt_version"] == ANALYSIS
        assert json.loads(t3.attempts[0]["raw_output"]) == raw_t3
        first_round = round_diagnostics(sent[1:3], original, kind)
        recovered_round = round_diagnostics(sent[3:5], recovered, None)
        assert first_round[0] != recovered_round[0]
        # 두 라운드의 내용을 섞거나 하나의 스냅샷으로 합치면 승인 진단으로 쓰지 못한다.
        with pytest.raises(ValueError):
            validate_diagnostics(
                recovered_round[1],
                service_input_sha256=first_round[0]["service_input_sha256"],
                source_snapshot=first_round[0],
                attempts=first_round[2],
            )
        combined = copy.deepcopy(first_round[0])
        combined["requests"].extend(recovered_round[0]["requests"])
        with pytest.raises(ValueError):
            validate_diagnostics(
                first_round[1],
                service_input_sha256=combined["service_input_sha256"],
                source_snapshot=combined,
                attempts=first_round[2],
            )
        context = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=interview.id,
            turn_no=2,
            limits=c.ContextLimits(2, 0, "fixture"),
        )
        restored = await prior_analyses(db, context.context)
        restored_json = json.loads(json.dumps(asdict(restored[str(original_turn.id)].data)))
        assert restored_json == first_analysis[0]
        report = await enrich_report_history(
            db,
            interview,
            [original_turn],
            {"turns": [{"turn_no": 1, "evidences": []}], "requirements": [], "limitations": []},
        )
        assert report["turns"][0]["analysis"] == first_analysis[0]
        await db.refresh(original_turn)
        await db.refresh(original)
        await db.refresh(t3)
        assert original_turn.analysis == first_analysis[0] and original_turn.answer_text == ANSWER
        assert (
            original.attempts == failed_audit[0]
            and json.loads(t3.attempts[0]["raw_output"]) == raw_t3
        )
