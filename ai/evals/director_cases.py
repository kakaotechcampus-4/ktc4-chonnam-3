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
