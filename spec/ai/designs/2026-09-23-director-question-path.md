# Director 기본 질문 생성·검증 경로

상태: **Accepted — 사용자 승인 첫 작업 범위 구현**. 2026-09-23 현재
`feature/ai-director-define`의 task-01~03 기반을 사용하며 다른 브랜치를 병합하지 않는다.
실제 모델·의미 검토기 품질과 BE 서비스 연결은 미검증이다.

## 완료 범위

호출자가 준비한 QuestionContract와 Context를 받아 질문 후보 하나를 생성하고,
독립 검토와 계약 검증을 통과한 질문 또는 typed failure를 반환한다.
목적 자동 선정, Persona quota 계산·턴 전환, Tool 실행, 자동 재작성·재계획,
DB 저장·WS 발행은 포함하지 않는다. 채택된 task-10 전체의 완료를 뜻하지 않는다.

정책 근거는 [면접 명세](../features/interviewer.md), ADR 0008·0010·0014·0015이며,
기존 Context/Question/QuestionContract/ModelResult의 저장·공개 형식은 유지한다.

## 호출 계약

구현: [agent.py](../../../ai/src/devon_ai/agents/director/agent.py)의 `generate_question`.

```python
result = await generate_question(
    context,
    question_contract,
    prompt=prompt,
    limits=limits,
    model_call=model_call,
    review=review,
    answer_analysis=checked_analysis,  # 생략 가능; 원시 분석 후보는 거절
    reference_texts=posting_sources,  # 생략 가능; {BasisRef: 검증된 원문}
)
```

- `model_call`은 task-03의 주입 callable이다. BE가 API key/client/공유 CallBudget을 바인딩한다.
- `prompt.task_name`은 `director`이며 version/model/template는 BE가 조회·주입한다.
- 반환형은 `ModelResult[ContractChecked[Question]]`이다. 새 DB/WS DTO가 아니다.
- `Context.turn_no`는 이 callable에 한해 **이번에 생성할 질문 번호**다. BE가 현재 답변의
  처리 완료와 대상 질문 번호를 확정해 전달한다. 첫 질문은 1이고 HR만 허용하며 이전 문답,
  현재 질문 계약·Turn ID·분석·사용한 Persona 횟수가 없어야 한다.
- 후속 질문은 입력된 허용 Persona를 사용한다. history 길이로 전체 턴 수를 추정하거나
  허용 Persona/최종 종료 상태를 AI에서 재계산하지 않는다.
- `answer_analysis`는 검증된 AnswerAnalysis만 허용하며 원문과 분리해 전달한다. 현재 문답과
  해당 분석의 연결, 준비 상태, 사용자 권한, 종료/중복 상태는 BE가 확인해야 한다.

## 생성과 검토

모델 입력은 `context`, `question_contract`, `reference_texts`, `answer_analysis` 네 항목이다.
모델의 `DirectorQuestion` schema version 2 출력은 persona·text·topic_code·evidence_refs·
jd_requirement_ids 다섯 필드다. `question_contract`를 모델에 다시 출력시키지 않고 Director
validator가 검증된 입력 원본을 결합해 기존 여섯 필드 Question을 만든다. 모델 출력에
`question_contract`나 다른 미소유 필드가 있으면 schema 실패다. topic_code는 비어 있지 않은
기존 문자열 필드를 유지하며 새 허용 enum·taxonomy를 만들지 않는다.

출력의 Evidence/JD ID는 Context에 등록된 자료이면서 준비된 `question_contract.basis_refs`의
같은 kind ID에 포함되어야 한다. 이는 준비된 계획 밖 자료를 모델이 새로 연결하지 못하게 하는
현재 질문 생성 경로의 정책이다. 모델이 실제 문장에 연결한 부분집합을 반환하되 필수 근거를
누락한 빈 목록을 정상으로 보충하지 않으며 독립 검토기가 문장과 참조의 실제 연결을 확인한다.
`validate_question_candidate`는 구조·정책 검사만 하며 검증 완료 객체를 만들지 않는다.

이후 `await review(request, candidate)`에 동일한 생성 입력·출처와 실제 후보를 전달한다.
검토기는 전제·현재 맥락·표현·필수 확인내용을 독립적으로 확인한 경우에만 기존 `QuestionReview`를
반환하고, 거절할 때는 `ContractError`를 발생시킨다. 모델 출력의 self-review를 사용하지 않는다.
현재 QuestionReview는 문장과 질문 계약에 결합되며 Persona·참조 검사는 별도로 선행한다.
항상 승인하는 테스트 검토기는 실제 자연어 의미 검토기의 구현·품질 증거가 아니다.

검토 결과와 후보의 문장·계약이 일치하고 기존 `validate_question`이 통과해야만
ContractChecked 결과를 반환한다. 실패 시 후보는 result.data에 남기지 않는다.
생성 모델이 계약을 출력하지 않아도 독립 검토에는 코드가 원본 계약을 붙인 완성 Question을
전달한다. 따라서 생성 출력의 중복 계약 비교는 제거하되 reviewer가 반환한 문장·계약과 실제
후보의 동등 비교는 유지한다. 생성 요청 JSON Schema와 validator는 다섯 필드 외 값을 거절한다.

## 출처와 호출 상한

- Evidence/JD/history ID 중복, 저장소 ID 중복, Evidence의 선택 repo·고정 SHA 불일치를
  호출 전에 거절한다. 준비된 basis_refs는 원문이 있는 등록 참조여야 한다.
- Evidence 원문, JD 요구사항 원문, 이전 답변 원문에서 참조 registry를 구성한다.
  Context에 공고 ID/본문 필드가 없으므로 job_posting 참조는 BE가 검증한 원문을 명시적으로
  추가해야 한다. 추가 원문으로 기존 참조 내용을 바꾸거나 Evidence/JD/history ID를 만들 수 없다.
- `Context.limits.remaining_calls`는 이 요청에 허용된 **남은 provider 시도 수**다.
  0이면 호출하지 않는다. `ModelRequest.max_attempts`에 `min(2, remaining_calls)`를 주입한다.
- `max_attempts` 기본값은 2이며 1 또는 2만 허용한다. 공통 호출 계층은 요청별 상한과
  기존 공유 CallBudget의 총 2회 상한을 동시에 지킨다. 기존 호출자의 기본 동작은 유지한다.
- parse/schema/timeout/provider 실패의 재시도는 공통 계층에만 있다. Director·검토 단계에는
  재시도가 없으며 semantic 실패 후 새 모델 호출을 하지 않는다.
- 독립 검토는 `limits.timeout_seconds` 이내로 제한한다. 이 값은 각 provider 시도와
  검토 단계에 각각 적용되며 전체 함수의 합산 deadline이 아니다. 검토기를 모델로 연결할 경우
  별도의 호출 승인·상한·metadata 연결을 마련해야 하며 이 구현이 추가 호출을 자동 수행하지 않는다.
- provider 시도 metadata는 성공·검토 실패 모두 보존한다. 검토 실패는 result.failure로 남으며
  이미 성공한 생성 시도를 실패한 provider 응답으로 고쳐 쓰지 않는다. 검토 비용·token은 미수집이다.

| 실패 위치 | 결과 |
| --- | --- |
| 잘못된 입력·참조 | `director_input_invalid`, 시도 없음 |
| 남은 호출 0 | budget 실패, 시도 없음 |
| 모델 transport/JSON/schema/semantic | 공통 CallFailure와 시도 기록 유지 |
| 주입 호출자가 반환한 정책 위반 후보 | `director_candidate_invalid` |
| 검토 거절·유효하지 않은 검토 결과 | semantic / `director_review_failed` |
| 검토 시간 초과 | timeout / `director_review_timeout` |

취소와 예상하지 못한 프로그래밍 오류는 상위 호출자에게 전파한다. 비밀값이나 검토 예외의
원문을 실패 설명으로 복사하지 않는다. 실패를 정상 finish나 일반 질문으로 대체하지 않는다.
위 오류 코드는 내부 반환값이다. 새로운 공개 API/WS reason을 추가한 것은 아니다.

## 프롬프트와 검증

[프롬프트 초안](../../../ai/prompts/director-question-v1.md)은 검수 전 자료다. AI runtime에서
자동 읽거나 기본값으로 사용하지 않는다. 담당자가 문구·실제 출력 품질을 검수한 뒤 BE의
PromptSpec/seed 경로로 주입한다. 실제 DB에 활성 prompt를 등록한 것은 아니다.

AI 테스트: `ai/tests/agents/director/test_director.py`.
BE HTTP adapter 연결 테스트: `backend/tests/integrations/test_director_boundary.py`.
정상 첫 HR/후속 질문, 모델 계약 재출력·계획 밖 출처·Persona 차단, 독립 검토 실패·취소·시간제한,
재시도 상한, 원문 전달, metadata와 평면 Turn JSONB 변환을 검사한다.
테스트는 provider/의미 검토기를 대체하며 실제 면접 서비스·모델 품질을 검증하지 않는다.
최종 실행 결과는 [AI 테스트 안내](../../../ai/docs/testing.md)에 기록한다.
