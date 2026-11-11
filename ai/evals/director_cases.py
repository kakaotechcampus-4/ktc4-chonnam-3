"""24개 합성 원문 그룹 × 5상황. 120개 독립 실사용 사례라고 해석하지 않는다."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from director_rubrics import SCENARIOS, compile_criteria
from eval_cases import Case
from judge_context import build_judge_context

VERSION = "director-study.v2"
CASE_VERSION = 2
LIMITATION = "합성 평가 원문이며 실제 운영·개인 기여·미제공 파일을 증명하지 않는다."

# 각 행이 독립 원문 그룹이고, 같은 행의 다섯 상황은 상관된 변형이다.
_PROFILES = (
    (
        "dev",
        "invoice",
        "python",
        "src/billing/invoice.py",
        "청구 기록",
        "def invoice(req):\n    validate(req)\n    return store.insert(req)\n",
    ),
    (
        "dev",
        "jobs",
        "typescript",
        "packages/worker/job.ts",
        "작업 기록",
        "export async function job(req) {\n  validate(req);\n  return store.insert(req);\n}\n",
    ),
    (
        "dev",
        "booking",
        "java",
        "booking/src/Booking.java",
        "예약 기록",
        "Booking reserve(Request req) {\n  validate(req);\n  return store.insert(req);\n}\n",
    ),
    (
        "dev",
        "webhook",
        "go",
        "internal/hooks/handler.go",
        "수신 이벤트",
        "func receive(req Request) error {\n"
        "  if err := validate(req); err != nil { return err }\n"
        "  return store.Insert(req)\n}\n",
    ),
    (
        "dev",
        "queue",
        "rust",
        "crates/tasks/src/queue.rs",
        "대기 작업",
        "fn enqueue(req: Request) -> Result<()> {\n"
        "    validate(&req)?;\n    store.insert(req)\n}\n",
    ),
    (
        "dev",
        "upload",
        "csharp",
        "Modules/Files/Upload.cs",
        "업로드 정보",
        "Task Upload(Request req) {\n  Validate(req);\n  return store.Insert(req);\n}\n",
    ),
    (
        "dev",
        "stock",
        "php",
        "app/Inventory/Stock.php",
        "재고 변경",
        "function update($req) {\n  validate($req);\n  return $this->store->insert($req);\n}\n",
    ),
    (
        "dev",
        "checkout",
        "ruby",
        "services/checkout.rb",
        "주문 요청",
        "def checkout(req)\n  validate(req)\n  store.insert(req)\nend\n",
    ),
    (
        "dev",
        "notify",
        "kotlin",
        "notification/Send.kt",
        "알림 요청",
        "fun send(req: Request): Record {\n  validate(req)\n  return store.insert(req)\n}\n",
    ),
    (
        "dev",
        "batch",
        "scala",
        "batch/Import.scala",
        "가져오기 작업",
        "def submit(req: Request): Record = {\n  validate(req)\n  store.insert(req)\n}\n",
    ),
    (
        "dev",
        "cache",
        "swift",
        "Sources/Cache/Refresh.swift",
        "갱신 요청",
        "func refresh(_ req: Request) throws -> Record {\n"
        "  try validate(req)\n  return try store.insert(req)\n}\n",
    ),
    (
        "dev",
        "profile",
        "dart",
        "lib/profile/update.dart",
        "프로필 변경",
        "Future<Record> update(Request req) async {\n"
        "  validate(req);\n  return store.insert(req);\n}\n",
    ),
    (
        "holdout",
        "shipment",
        "python",
        "delivery/accept.py",
        "배송 접수",
        "def accept(parcel):\n    check_address(parcel)\n    return deliveries.save(parcel)\n",
    ),
    (
        "holdout",
        "ticket",
        "typescript",
        "apps/tickets/submit.ts",
        "문의 접수",
        "export function submit(ticket) {\n"
        "  checkCategory(ticket);\n  return tickets.save(ticket);\n}\n",
    ),
    (
        "holdout",
        "payment",
        "java",
        "pay/core/Accept.java",
        "결제 요청",
        "Payment accept(Request payment) {\n"
        "  checkAmount(payment);\n  return payments.save(payment);\n}\n",
    ),
    (
        "holdout",
        "account",
        "go",
        "accounts/create.go",
        "계정 등록",
        "func Create(account Account) error {\n"
        "  if err := checkEmail(account); err != nil { return err }\n"
        "  return accounts.Save(account)\n}\n",
    ),
    (
        "holdout",
        "search",
        "rust",
        "indexer/src/accept.rs",
        "색인 요청",
        "fn accept(document: Document) -> Result<()> {\n"
        "    check_fields(&document)?;\n    index_jobs.save(document)\n}\n",
    ),
    (
        "holdout",
        "media",
        "csharp",
        "Media/Submit.cs",
        "변환 요청",
        "Task Submit(Media media) {\n  CheckFormat(media);\n  return conversions.Save(media);\n}\n",
    ),
    (
        "holdout",
        "coupon",
        "php",
        "Domain/Coupon/Issue.php",
        "쿠폰 발급",
        "function issue($coupon) {\n"
        "  checkPeriod($coupon);\n  return $this->coupons->save($coupon);\n}\n",
    ),
    (
        "holdout",
        "ledger",
        "ruby",
        "ledger/record.rb",
        "원장 기록",
        "def record(entry)\n  check_balance(entry)\n  ledger.save(entry)\nend\n",
    ),
    (
        "holdout",
        "route",
        "kotlin",
        "routing/Register.kt",
        "경로 등록",
        "fun register(route: Route): Record {\n"
        "  checkStops(route)\n  return routes.save(route)\n}\n",
    ),
    (
        "holdout",
        "metrics",
        "scala",
        "analytics/Ingest.scala",
        "지표 수집",
        "def ingest(metric: Metric): Record = {\n"
        "  checkLabels(metric)\n  metrics.save(metric)\n}\n",
    ),
    (
        "holdout",
        "calendar",
        "swift",
        "Calendar/Add.swift",
        "일정 추가",
        "func add(_ event: Event) throws -> Record {\n"
        "  try checkTime(event)\n  return try events.save(event)\n}\n",
    ),
    (
        "holdout",
        "form",
        "dart",
        "features/forms/send.dart",
        "신청서 접수",
        "Future<Record> send(Form form) async {\n"
        "  checkFields(form);\n  return forms.save(form);\n}\n",
    ),
)


def content_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Cohort:
    cases: tuple[Case, ...]
    pilot_ids: tuple[str, ...]
    manifest: dict[str, Any]

    def select(self, selection: str) -> tuple[Case, ...]:
        if selection not in {"pilot", "dev", "holdout", "all"}:
            raise ValueError("invalid Director selection")
        if selection == "pilot":
            return tuple(case for case in self.cases if case.case_id in self.pilot_ids)
        return tuple(case for case in self.cases if selection == "all" or case.split == selection)


def _case(profile: tuple[str, ...], scenario: str, number: int) -> Case:
    split, name, _language, path, action, code = profile
    group = f"director-{split}-{name}-v1"
    case_id = f"dq-{number:02d}-{scenario}"
    turn_id, evidence_id, repo_id = f"{case_id}-t2", f"{group}-e1", f"{group}-repo"
    git_ref = hashlib.sha1(
        code.encode()
    ).hexdigest()  # 합성 원문 식별자이며 실재 Git commit이 아니다.
    flow = f"요청을 검증한 뒤 {action} 저장을 호출합니다."
    failure = "실패하면 오류를 기록하고 동일 요청 ID로 중복 저장을 막으며 재시도하겠습니다."
    answer = {
        "partial": flow,
        "sufficient": f"{flow} {failure}",
        "dont_know": "이 처리 흐름과 장애 처리 방식은 모르겠습니다.",
        "contribution_correction": (
            f"{flow} 제가 맡은 부분은 요청 검증이고 저장과 예외 처리는 팀원이 구현했습니다."
        ),
        "tool_unavailable": f"{flow} 장애 처리 구현은 아직 확인하지 못했습니다.",
    }[scenario]
    sufficient, unknown = scenario == "sufficient", scenario == "dont_know"
    contract = {
        "purpose": "요청 처리 흐름과 실패 시 접근을 확인한다.",
        "required_points": [
            {"key": "flow", "description": "원문에 보이는 검증과 저장 순서"},
            {"key": "failure", "description": "저장 실패를 가정한 확인·대응 접근"},
        ],
        "assumptions": ["실패 대응은 가정형이며 실제 구현을 전제하지 않는다."],
        "basis_refs": [{"kind": "evidence", "id": evidence_id}],
        "evaluation_scope": "제공된 정적 코드 흐름과 가정한 실패 대응 설명만 확인한다.",
        "evaluation_keys": ["project_understanding", "communication"],
    }
    question = {
        "persona": "tech_lead",
        "text": "이 요청은 어떤 순서로 처리되며, 저장이 실패한다면 어떻게 확인하시겠어요?",
        "topic_code": "request-flow",
        "question_contract": contract,
        "evidence_refs": [evidence_id],
        "jd_requirement_ids": [],
        "question_type": "main",
        "parent_turn_id": None,
    }
    covered = [] if unknown else [{"key": "flow", "answer_quotes": [flow]}]
    if sufficient:
        covered.append({"key": "failure", "answer_quotes": [failure]})
    limits = [LIMITATION, "제공된 구간에는 실제 운영 결과와 완전한 실패 경로가 없다."]
    tools = []
    if scenario == "tool_unavailable":
        tools = [
            {
                "status": "tool_error",
                "items": [],
                "searched_scope": [path],
                "limitations": ["추가 원문 조회가 실패했다. 미확인 구현은 부재로 확정하지 않는다."],
                "error_code": "synthetic_source_unavailable",
            }
        ]
    context: dict[str, Any] = {
        "interview_id": case_id,
        "current_turn_id": turn_id,
        "turn_no": 3,
        "total_turns": 9,
        "persona_counts": [
            {"persona": "hr_manager", "count": 1},
            {"persona": "tech_lead", "count": 1},
            {"persona": "domain_lead", "count": 0},
        ],
        "allowed_personas": ["tech_lead", "domain_lead"],
        "jd_requirements": [
            {
                "id": f"{group}-jd",
                "text": "서비스 요청 처리와 장애 대응을 설명할 수 있는 개발자",
                "category": "required",
                "source_field": "jd_requirements.text",
                "tech_tags": [],
            }
        ],
        "repositories": [
            {
                "repository_id": repo_id,
                "git_ref": git_ref,
                "primary": True,
                "analysis_refs": [],
                "limitations": limits,
            }
        ],
        "history": [
            {
                "turn_id": f"{case_id}-t1",
                "persona": "hr_manager",
                "question": "이 프로젝트에서 본인과 팀의 역할을 소개해 주세요.",
                "answer": "제가 요청 처리 기능을 구현했습니다.",
                "analysis_ref": None,
            },
            {
                "turn_id": turn_id,
                "persona": "tech_lead",
                "question": question["text"],
                "answer": answer,
                "analysis_ref": turn_id,
            },
        ],
        "current_question_contract": contract,
        "evidence": [
            {
                "evidence_id": evidence_id,
                "repository_id": repo_id,
                "git_ref": git_ref,
                "source_kind": "code",
                "path": path,
                "metadata_key": None,
                "content": code,
                "tool_name": None,
                "summary": None,
                "start_line": 1,
                "end_line": len(code.splitlines()),
            }
        ],
        "domain_frames": [
            {
                "id": f"{group}-frame",
                "category": "etc",
                "version": "synthetic-v1",
                "text": "가정한 서비스에서 장애 영향과 데이터 일관성 확인 방법을 묻는다.",
            }
        ],
        "limits": {"remaining_calls": 2, "remaining_replans": 0, "policy_version": VERSION},
        "evaluation_targets": [
            {"persona": "tech_lead", "keys": ["technical_reasoning", "communication"]},
            {"persona": "domain_lead", "keys": ["company_job_fit", "communication"]},
        ],
        "supplemental_sources": [],
        "external_searches": [],
        "supplemental_limitations": limits,
        "presented_evaluation_keys": [
            "contribution_clarity",
            "communication",
            "project_understanding",
        ],
    }
    analysis = {
        "evaluation_status": "evaluated",
        "sufficiency": "sufficient" if sufficient else "insufficient" if unknown else "partial",
        "covered_points": covered,
        "missing_points": [] if sufficient else ["flow", "failure"] if unknown else ["failure"],
        "technical_assessment": {
            "explanation": "질문 계약과 합성 답변 원문에 한정한 관찰이다.",
            "answer_quotes": [answer],
            "evidence_refs": [evidence_id],
            "limitations": limits,
        },
        "contribution_scope": {
            "scope": "shared" if scenario == "contribution_correction" else "unknown",
            "answer_quotes": [answer] if scenario == "contribution_correction" else [],
        },
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": limits,
        "external_queries": [],
    }
    rubric = compile_criteria(scenario)
    expectation = {
        "case_id": case_id,
        "version": CASE_VERSION,
        "allowed": rubric["allowed"],
        "forbidden": rubric["forbidden"],
        "grader_controls": [],
        "source_fact": f"synthetic:{group}:{scenario}",
        "review": {
            "status": "unreviewed",
            "author": "codex",
            "reviewer": None,
            "reviewed_at": None,
            "pending_notes": [],
        },
    }
    payload = {
        "service_task": "director",
        "service_input": {
            "context": context,
            "question": question,
            "answer_text": answer,
            "answer_analysis": analysis,
            "allowed_locations": [[repo_id, git_ref, path]],
            "tool_results": tools,
            "reference_texts": [
                {
                    "kind": "job_posting",
                    "id": f"{group}-posting",
                    "text": json.dumps(
                        {
                            "position": "서비스 개발자",
                            "requirements": "서비스 요청 처리와 장애 대응 설명",
                            "collector_debug": {"source": "synthetic", "run": "not_model_evidence"},
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        },
    }
    return Case(case_id, CASE_VERSION, "question", split, group, payload, expectation)


def build_cohort() -> Cohort:
    cases = tuple(
        _case(profile, scenario, number)
        for number, profile in enumerate(_PROFILES, 1)
        for scenario in SCENARIOS
    )
    pilot = tuple(cases[index * 5 + index % 5].case_id for index in range(12))
    manifest = {
        "version": VERSION,
        "synthetic": True,
        "independent_real_repositories": 0,
        "source_groups": 24,
        "cases_per_group": 5,
        "pilot_ids": list(pilot),
        "case_payload_sha256": {case.case_id: content_hash(case.payload) for case in cases},
        "case_expectation_sha256": {case.case_id: content_hash(case.expectation) for case in cases},
        "rubric_protocol": compile_criteria("partial")["protocol"],
        "limitations": [
            LIMITATION,
            "같은 source group의 변형을 독립 표본으로 계산하지 않는다.",
            "60/60/12/24는 실행 규모이며 통계적 충분성이나 수치 합격선의 근거가 아니다.",
        ],
    }
    cohort = Cohort(cases, pilot, manifest)
    validate_cohort(cohort)
    return cohort


def validate_cohort(cohort: Cohort) -> None:
    identities: set[str] = set()
    groups: dict[str, str] = {}
    source_texts: dict[str, str] = {}
    for case in cohort.cases:
        if case.case_id in identities:
            raise ValueError("duplicate Director case")
        identities.add(case.case_id)
        if groups.setdefault(case.source_group_id, case.split) != case.split:
            raise ValueError("source group leaks across splits")
        for item in case.payload["service_input"]["context"]["evidence"]:
            digest = content_hash(item["content"])
            if source_texts.setdefault(digest, case.split) != case.split:
                raise ValueError("source text leaks across splits under a different ID")
    if not set(cohort.pilot_ids) <= {case.case_id for case in cohort.cases if case.split == "dev"}:
        raise ValueError("pilot must be a subset of development cases")
    if cohort.manifest["case_payload_sha256"] != {
        case.case_id: content_hash(case.payload) for case in cohort.cases
    } or cohort.manifest["case_expectation_sha256"] != {
        case.case_id: content_hash(case.expectation) for case in cohort.cases
    }:
        raise ValueError("cohort manifest binding mismatch")


def export_cohort(cohort: Cohort, destination: Path) -> None:
    """원본을 덮어쓰지 않고 기존 load_cases가 읽는 형식으로 물질화한다."""
    validate_cohort(cohort)
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ("inputs", "expectations"):
        (destination / folder).mkdir(exist_ok=True)
    for case in cohort.cases:
        stem = f"{case.case_id}.v{case.version}.json"
        inp = {
            "case_id": case.case_id,
            "version": case.version,
            "control": {
                "kind": case.kind,
                "split": case.split,
                "source_group_id": case.source_group_id,
                "synthetic": True,
            },
            "payload": case.model_input(),
        }
        for folder, value in (("inputs", inp), ("expectations", case.expectation)):
            with (destination / folder / stem).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    with (destination / "cohort-manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(cohort.manifest, ensure_ascii=False, indent=2) + "\n")


def control_packets(cohort: Cohort) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """기대 라벨은 검토 자료와 분리한다. 모호 control은 계약이 없는 부분 관측이다."""
    packets, labels = [], {}
    for index, case in enumerate(cohort.select("pilot")[:8]):
        rubric = {key: copy.deepcopy(case.expectation[key]) for key in ("allowed", "forbidden")}
        question = copy.deepcopy(case.payload["service_input"]["question"])
        question["text"] = "같은 요청이 동시에 두 번 들어온다면 중복 처리를 어떻게 막겠어요?"
        question["question_contract"].update(
            purpose="가정한 동시 중복 요청의 처리 경계",
            required_points=[{"key": "concurrency", "description": "동시 중복 요청을 막는 경계"}],
            evaluation_scope="새로 제시한 동시 요청 조건에서 가정한 대응만 관찰한다.",
            evaluation_keys=["technical_reasoning", "communication"],
        )
        good = json.dumps({"question": question}, ensure_ascii=False)
        bad = copy.deepcopy(question)
        bad["text"] = "직접 구현해 초당 10만 건을 처리한 Redis 분산 잠금의 성과를 설명해 주세요."
        candidates = (
            ("accept", good),
            ("reject", json.dumps({"question": bad}, ensure_ascii=False)),
            (
                "ambiguous",
                json.dumps(
                    {
                        "question": {"text": question["text"]},
                        "limitations": [
                            "생성 당시 질문 계약은 기록에 없어 문장·계약 일치를 판단할 수 없다."
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        context = build_judge_context(case.model_input())
        for position, (verdict, output) in enumerate(candidates):
            identifier = f"dc-{index + 1:02d}-{position + 1}"
            labels[identifier] = verdict
            packets.append(
                {
                    "case": identifier,
                    "rubric": copy.deepcopy(rubric),
                    "candidate_output": output,
                    "source_context": context,
                    "binding": {
                        "rubric_sha256": content_hash(rubric),
                        "candidate_sha256": content_hash(output),
                        "source_context_sha256": content_hash(context),
                    },
                }
            )
    return packets, labels
