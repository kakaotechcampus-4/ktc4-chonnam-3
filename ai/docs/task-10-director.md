# task-10 - Director 질문 결정

상태: 구현 가이드. 현재 runtime은 docstring 스켈레톤이며 Director 동작은 미구현이다.

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
- [내부 계약](../../spec/ai/contracts.md)의 Question과 DirectorDecision은 Proposed다. fixture로
  검토할 수 있지만 AI-L02 승인 전 production schema나 저장 enum으로 채택하지 않는다.
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
- [ ] 실제 계약 채택이 필요하면 AI-L02, 호출 budget이 필요하면 AI-L04를 먼저 결정한다.

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
- [ ] `tech_lead` 목표 6턴·최소 5턴, `domain_lead + hr_manager` 합산 최소 3턴을 지킨다.
- [ ] HR과 domain의 개별 최소 횟수나 고정 교대 규칙을 새로 만들지 않는다.
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

추가 예정, 현재 없음: `ai/tests/agents/director/test_director.py`.

- [ ] 첫 질문 HR, 9번째 답변 후 종료, 10번째 질문 없음의 대조 사례를 둔다.
- [ ] 남은 턴으로 quota를 불가능하게 하는 Persona 후보가 Controller에서 제외되는지 검사한다.
- [ ] 허용되지 않은 Persona, 없는 Evidence, 잘못된 ref와 Contract 불일치 후보를 거절한다.
- [ ] 깨진 JSON, 계약 누락, 구조는 맞지만 허용 Persona·ref를 어긴 후보를 parse/schema/semantic 실패로 구분하고 default로 보충하지 않는다.
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
| AI-L02 내부 계약 | Proposed fixture와 의미 검증 | 필드·enum·null·저장 위치 공동 채택 |
| AI-L04 실행 상한 | ADR 0008 실패 분류·복구 선택 fixture | 실제 재호출 여부·횟수, Tool·재작성·재계획 budget과 책임 확정 |
| AI-L09 서비스 복구·턴 배분 | rewrite/replan/failure 선택 검사 | 실제 반환 계약, 사용자 입력·서비스 상태 복구, HR/domain 배분과 공개 동작 확정 |
| AI-L10 domain 운영 | `etc`, 맥락 관련성·목적 비반복 fixture | 운영 문구·검수·version·저장 방식 승인 |
| AI-L11~L14 BE/WS | 순수 후보와 단일 연결 fixture | worker, 멱등성, WS 식별·복구 계약을 각 담당과 확정 |

대기 항목의 현재 상태는 [later.md](../../later.md)에서 확인한다.
