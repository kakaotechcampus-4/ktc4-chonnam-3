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
