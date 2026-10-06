# task-10 - Director 질문 결정

상태: 준비된 질문 목적을 받는 기본 생성·독립 검토·검증 경로 구현. 목적 자동 선정·도구 실행·턴 전환·BE 서비스 연결은 후속 범위다.

## 현재 구현

`generate_question`은 기존 Context/QuestionContract와 주입 모델 호출·검토기를 사용해
`ModelResult[ContractChecked[Question]]` 또는 실패를 반환한다.
모델의 `DirectorQuestion` schema version 2 출력은 persona·text·topic_code·evidence_refs·
jd_requirement_ids 다섯 필드만 받는다. 입력 QuestionContract 원본은 코드가 결합해 기존
여섯 필드 Question을 만들며, 모델이 계약을 다시 출력하거나 바꾸게 하지 않는다.
[첫 구현 인계](../../spec/ai/designs/2026-09-23-director-question-path.md)에 입력과 책임,
참조 검사, 요청별 시도 상한, 검토 실패와 [프롬프트 초안](../prompts/director-question-v1.md)을 기록했다.
실제 의미 검토기와 provider 품질은 아직 검증하지 않았다. 아래 체크리스트는 전체 task 범위다.

## 목표

단일 Director가 검증된 Context와 답변 분석을 받아 다음 질문의 관점과 목적을 제안하게 한다.
질문 수, 허용 Persona, 현재 Turn과 종료 여부는 BE Controller가 확정하며 Director가 서비스
상태를 대신 결정하지 않는다.

전체 순서는 [AI 구현 파이프라인](pipeline.md)을 따른다. 선행 작업은
[task-02 계약](task-02-contracts.md), [task-03 LLM 경계](task-03-llm-boundary.md),
[task-06 입력 준비](task-06-context-preparation.md),
[task-07 도메인 프레임](task-07-domain-frames.md),
[task-08 근거 도구](task-08-evidence-tools.md),
[task-09 답변 분석](task-09-answer-analysis.md)이다.

## 근거

- [Director와 텍스트 면접](../../spec/ai/features/interviewer.md)의 역할과 입력, 고정 9턴
  정책, 질문 생성과 검증, 답변부터 다음 질문까지를 따른다.
- Persona 횟수는 [공통 0004 결정](../../spec/shared/decisions/0004-flexible-persona-allocation-restoration.md)의 기술 목표 6턴·최소 5턴, 도메인·HR 합산 최소 3턴을 따른다. 도메인과 HR의 개별 횟수는 고정하지 않는다.
- [내부 계약](../../spec/ai/contracts.md)의 질문 기준·기존 DirectorDecision은 [0014](../../spec/ai/decisions/0014-minimal-change-revision.md), Context·Question·Evidence 기본 구성과 ToolResult 부분 오류 처리는 [0015](../../spec/ai/decisions/0015-existing-contracts-and-tool-results.md)를 따른다.
  미채택 상세 타입·행동별 표현·Tool 인수는 기존 구조에 맞춰 구체화하고 fixture로 검토한다.
- [도메인 질문 정책](../../spec/ai/decisions/0005-domain-question-policy.md)과
  [답변 정성 평가 정책](../../spec/ai/decisions/0004-answer-assessment-policy.md)의 Accepted
  의미를 유지한다.
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 질문 복구와
  domain frame 우선순위를 적용한다.
- [BE task-14](../../backend/docs/task-14-agents.md)와
  [BE task-15](../../backend/docs/task-15-interview-ws.md)의 단일 Director와 텍스트 Turn
  흐름을 연결 대상으로 삼는다.

## 선행 조건

- [ ] Context가 현재 사용자, 면접, 선택 repo와 고정 SHA에 한정됐는지 확인한다.
- [ ] 첫 질문 전 준비 조건과 `preparing_failed` 처리가 BE에서 검증됐는지 확인한다.
- [ ] Question, AnswerAnalysis, Evidence fixture의 출처와 미확인 범위를 구분한다.
- [ ] Controller가 계산한 허용 Persona와 남은 질문 수를 입력으로 받을 수 있게 한다.
- [ ] AI-L02의 채택된 계약을 사용하고 미채택 상세를 구체화한다. 실제 호출 전에는 AI-L04의 유한한 실행 설정과 소진 처리를 확인한다.

## 대상 파일과 책임

- [Director 원본](../src/devon_ai/agents/director/agent.py): 다음 질문의 Persona, 목적,
  보완·심화·전환 후보를 제안한다.
- [Director 도구 경계](../src/devon_ai/agents/director/tools.py): task-08에서 승인된 제한 Tool
  요청과 결과를 Director가 해석하는 경계다.
- [AI 계약 위치](../src/devon_ai/contracts.py): 승인된 내부 타입만 둔다. task-10에서 임의
  DTO나 enum을 먼저 만들지 않는다.
- [BE Director 연결](../../backend/app/agents/director/agent.py): 상태 재확인, 허용 Persona,
  저장과 전달을 맡는 얇은 연결 계층이다.
- [BE 면접 service](../../backend/app/features/interview/turn_service.py): 현재 Turn, 중복,
  종료와 transaction을 확정한다.

Persona마다 별도 Agent나 class를 만들지 않는다. `hr_manager`, `tech_lead`, `domain_lead`는
한 Director가 선택하는 관점이며 새 package나 Question Generator Agent를 추가하지 않는다.

## 작업

- [ ] 질문 하나와 답변 하나를 한 Turn으로 계산하고 Tool 호출·재작성은 Turn에 넣지 않는다.
- [ ] 첫 질문은 `hr_manager`로 고정하고, 코드 Evidence 없이 자기소개를 물을 수 있게 한다.
- [ ] 2번째 질문부터 Controller가 준 허용 Persona 안에서만 후보를 선택한다.
- [ ] 정상 흐름은 9번째 답변 처리 뒤 종료하며 9번째 질문 전송만으로 끝내지 않는다.
- [ ] 정상 9턴에서 `tech_lead` 목표 6턴·최소 5턴과 `domain_lead + hr_manager` 합산 최소 3턴을 지킨다.
- [ ] 도메인·HR의 개별 횟수와 질문 순서를 고정하지 않고, 2번째 질문부터 허용 Persona 중 답변 맥락에 맞춰 선택한다. 첫 HR 질문 뒤에도 HR을 선택할 수 있다.
- [ ] 질문 목적, 필수 확인내용, 가정과 유효한 근거 참조를 먼저 구성한다.
- [ ] ID·Persona·남은 턴·참조 유효성처럼 결정 가능한 조건은 Controller 검사로 남긴다.
- [ ] 전제·목적·필수 확인내용이 유효하고 표현만 복합적·유도적이면 의미를 보존한 rewrite 후보로 분류한다.
- [ ] 거짓·stale 전제나 이미 확인한 목적의 반복은 새로운 목적·근거의 replan 후보로 분류한다.
- [ ] 허용 Persona·맥락·근거 안에서 안전한 후보가 없으면 failure를 반환하고 invalid fallback이나 정상 `finish`로 바꾸지 않는다.
- [ ] 한 질문에 중심 목적 하나만 남기고 복합 질문, 정답 유도, 표현만 바꾼 반복을 막는다.
- [ ] 보완 질문은 이전 답변의 부족한 부분, 심화 질문은 새로운 판단 조건에 연결한다.
- [ ] 후속 보완과 기여 정정을 반영하되 이전 답변 원문과 최초 분석을 바꾸지 않는다.
- [ ] `answer_vs_code`는 거짓 단정이 아닌 버전·조건 확인형 후속 질문으로 다룬다.
- [ ] domain 입력이 없거나 신뢰하기 어려우면 산업을 추측하지 않고 `etc`를 사용한다.
- [ ] 적격 domain frame은 검증된 맥락 관련성, 같은 관련성에서는 이전 질문 목적의 비반복 순으로 선택한다.
- [ ] domain 축 고정 순환·축별 최소·relevance 점수·모든 축 소진 의무를 만들지 않는다.
- [ ] domain 질문은 미확인 경험을 가정형으로 표현하고 JD 검사·전문가 정답·점수를 만들지 않는다.
- [ ] 모델의 `finish` 제안은 Controller가 정상 종료 조건을 확인한 경우에만 수용한다.
- [ ] 검증 실패나 budget 소진 때 실패한 질문을 fallback으로 사용자에게 내보내지 않는다.

## 검증

현재 존재: `ai/tests/agents/director/test_director.py`,
`backend/tests/integrations/test_director_boundary.py`.
기본 생성 경로의 fixture·HTTP adapter 검사이며 아래 전체 턴 정책·서비스 검사의 완료를 뜻하지 않는다.

- [ ] 첫 질문 HR, 9번째 답변 후 종료, 10번째 질문 없음의 대조 사례를 둔다.
- [ ] Controller가 이미 확정·제시한 횟수와 남은 턴을 확인해 기술 최소 5턴·도메인과 HR 합산 최소 3턴을 충족할 수 있는 Persona만 허용하는지 검사한다. 최소 조건을 충족할 수 있는 HR 재선택을 고정 할당으로 막지 않는다.
- [ ] 허용되지 않은 Persona, 없는 Evidence, 잘못된 ref와 준비된 Contract 범위 밖 참조 후보를 거절한다.
- [ ] 깨진 JSON, 모델이 추가한 `question_contract`·필드 누락, 구조는 맞지만 허용 Persona·ref를 어긴 후보를 parse/schema/semantic 실패로 구분하고 default로 보충하지 않는다.
- [ ] 충분한 답변 반복, 후속 보완, 기여 정정, Persona 전환 뒤에도 기록 연결을 유지한다.
- [ ] domain `etc` fallback, 중심 목적, 가정형 표현과 기술 질문 중복 방지를 검사한다.
- [ ] Tool·재계획 실패가 질문 중복 확정이나 무제한 호출로 이어지지 않는지 검사한다.
- [ ] 같은 목적의 defective wording, 거짓·stale·중복 전제, 안전한 후보 없음이 각각 rewrite/replan/failure로 분류되는지 검사한다.
- [ ] domain 후보가 맥락 관련성과 목적 비반복 순으로 선택되고 고정 축 순환이 생기지 않는지 검사한다.
- [ ] 사용자 종료 중 늦은 결과는 BE 통합 검사에서 저장·전달되지 않는지 확인한다.

Mock과 policy fixture 통과는 실제 provider 품질, DB 저장, WS 전달이나 9턴 통합 완료가 아니다.

## 완료 조건

- [ ] 단일 Director의 순수 결정 경계와 BE Controller 소유권이 코드와 테스트에서 분리된다.
- [ ] 승인된 9턴·Persona·질문 검증·후속 보완 정책의 대조 fixture가 통과한다.
- [ ] 내부 결정 객체를 공개 WS payload로 직접 직렬화하지 않는다.
- [ ] 미결정 계약·상한·복구 정책을 임의 값으로 채우지 않고 보류 결과에 남긴다.

## 결정 대기와 재개 조건

| 항목 | 지금 가능한 작업 | production 연결 재개 조건 |
| --- | --- | --- |
| AI-L02 내부 계약 | 기존 여섯 판단 필드와 ask/retrieve/finish, reason_summary의 실제 조회 요약 검토 | 미채택 상세 객체·행동별 null·ToolResult·공개 변환 확정; 영구 실패 기록 위치는 AI-L18, 복구는 AI-L12와 함께 검토 |
| AI-L04 실행 상한 | ADR 0008 실패 분류·복구 선택 fixture | 공통 LLM 호출 총 2회·semantic 재호출 금지 유지, Tool·재작성·재계획 budget과 소진 처리의 구현·측정 |
| AI-L09 서비스 연결 | rewrite/replan/failure 선택, 정상 9턴·기술 목표 6턴·최소 5턴과 도메인·HR 합산 최소 3턴 검사 | 기존 반환·오류 안내·기록 보존·명시적 종료 연결 검증; Director는 최소 조건을 충족할 수 있는 후보 중 답변 맥락에 따라 선택하며 새 수동 이어가기 없음 |
| AI-L10 domain 운영 | `etc`, 맥락 관련성·목적 비반복 fixture | 운영 문구·검수·version·저장 방식 승인 |
| AI-L11~L14 BE/WS | 순수 후보와 단일 연결 fixture | worker, 멱등성, WS 식별·복구 계약을 각 담당과 확정 |

채택한 방향은 [AI 결정 기록](../../spec/ai/decisions/README.md), 남은 실제 작업은 [구현·검수 인계](pipeline.md#기존-id별-구현검수-인계)에서 확인한다.
