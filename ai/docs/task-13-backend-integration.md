# task-13 - Backend 통합과 인계

상태: 구현 가이드. AI package 설치 smoke만 존재하며 실제 facade·service 연결은 미구현이다.

## 목표

검증된 AI callable을 기존 BE API·pipeline·worker·텍스트 WS에 연결한다. 이 작업은
[task-06 입력 준비](task-06-context-preparation.md)의 readiness 조정과 다르다. task-06은
호출 가능한 입력을 준비하고, task-13은 승인된 계약을 실제 I/O·상태·저장 흐름에 인계한다.

전체 순서와 task별 gate는 [AI 구현 파이프라인](pipeline.md)을 따른다. 관련 AI 작업은
[task-02 계약](task-02-contracts.md), [task-03 LLM 경계](task-03-llm-boundary.md),
[task-04 L1](task-04-repo-shallow.md), [task-05 L2](task-05-repo-deep.md),
[task-06 입력 준비](task-06-context-preparation.md), [task-07 도메인](task-07-domain-frames.md),
[task-08 근거](task-08-evidence-tools.md), [task-09 답변](task-09-answer-analysis.md),
[task-10 Director](task-10-director.md), [task-11 리포트](task-11-report.md)다.

## 근거

- [AI Context](../../spec/ai/features/job-context.md)의 LLM 경계, ARQ 전달, 멱등성과 stale
  결과 차단을 따른다.
- [Director 흐름](../../spec/ai/features/interviewer.md)과
  [리포트 흐름](../../spec/ai/features/report-profile.md)의 Controller·worker 소유권을 유지한다.
- [BE pipeline](../../backend/docs/pipeline.md), [BE task-14](../../backend/docs/task-14-agents.md),
  [BE task-15](../../backend/docs/task-15-interview-ws.md),
  [BE task-16](../../backend/docs/task-16-report.md)를 실제 통합 기준으로 함께 검토한다.
- [0006 LLM 사용 정책](../../spec/ai/decisions/0006-task-llm-usage-policy.md)의 Wanted 변환과
  profile 확정 집계 비호출 원칙을 지킨다.

## 선행 조건

- [ ] 연결할 AI task의 callable, typed 성공·실패와 의미 검증이 독립 테스트를 통과한다.
- [ ] task별 AI-L02 계약 채택 범위와 BE 변환·저장 위치가 명시된다.
- [ ] 실제 provider/model과 prompt/config 조회는 AI-L01 결정 및 검증 뒤 연결한다.
- [ ] timeout·token·Tool·재시도 상한과 attempt 소유 계층은 AI-L04 결정 뒤 적용한다.
- [ ] 해당 흐름의 AI-L11~AI-L17 gate를 해결하거나 미해결 부분을 보류로 분리한다.
- [ ] 연결 전후 현재 사용자, run/interview, 선택 repo, SHA와 input version을 재확인한다.

## 대상 파일과 책임

- [AI 계약 원본](../src/devon_ai/contracts.py): BE가 전달할 승인된 내부 타입의 원본이다.
- [AI Director](../src/devon_ai/agents/director/agent.py)와
  [AI Tool 경계](../src/devon_ai/agents/director/tools.py): 주입된 값으로 후보를 반환한다.
- [AI L1](../src/devon_ai/llm_tasks/repo_shallow.py),
  [AI L2](../src/devon_ai/llm_tasks/repo_deep.py),
  [AI 답변](../src/devon_ai/llm_tasks/answer_analysis.py),
  [AI 리포트](../src/devon_ai/llm_tasks/report.py): DB session 없이 실행되는 task 원본이다.
- [BE AI 계약](../../backend/app/agents/contracts.py),
  [BE Director](../../backend/app/agents/director/agent.py),
  [BE Director Tool](../../backend/app/agents/director/tools.py): service와 AI 사이의 얇은 adapter다.
- [BE LLM client](../../backend/app/integrations/llm/client.py)와
  [prompt loader](../../backend/app/llm_tasks/prompt_loader.py): provider I/O, 실제 model·prompt 설정을 소유한다.
- [BE interview service](../../backend/app/features/interview/service.py),
  [turn service](../../backend/app/features/interview/turn_service.py),
  [WS handler](../../backend/app/features/interview/ws.py): 권한·현재 상태·저장·공개 메시지를 소유한다.
- [BE report service](../../backend/app/features/report/service.py)와
  [ARQ 설정](../../backend/app/workers/arq_app.py): lazy 생성, enqueue와 worker 등록을 소유한다.

새 AI server, provider package, gateway package, Controller, worker나 Context Builder Agent를
추가하지 않는다. 현재 BE 연결 파일이 docstring이라는 이유로 미승인 facade signature를 만든다거나
AI source를 BE에 복사하지 않는다.

## 작업

- [ ] BE가 DB에서 권한·상태·선택 범위를 검증한 뒤 필요한 값만 AI 계약으로 변환한다.
- [ ] `AsyncSession`, ORM 객체, access token, Redis client와 provider client를 AI에 넘기지 않는다.
- [ ] `prompt_loader`가 DB의 prompt와 model 설정을 읽고 adapter가 이를 AI task에 주입한다.
- [ ] provider 호출 metadata와 실패는 승인된 저장·보호 범위에서 기록하고 일반 로그에 원문을 남기지 않는다.
- [ ] L1/L2, 답변 분석, Director, report의 기존 LLM 방향과 일곱 version 이름을 유지한다.
- [ ] Wanted 구조화 필드 변환은 기존 규칙으로 수행하고 누락을 LLM 추측으로 채우지 않는다.
- [ ] `profile_summary`는 report 성공 뒤 실행하되 확정 데이터 집계만 하고 LLM을 호출하지 않는다.
- [ ] 추천은 최대 5개 FIX와 근거 연결만 유지하고 AI-L07 전 산식·정렬·미계산 표시를 발명하지 않는다.
- [ ] 현재 FIX job은 `initial_sync`, `analysis_run`, `candidate_page_analyze`, `interview_prep`,
  `report_generate`, `profile_summary` 여섯 개임을 기준으로 등록과 enqueue를 검사한다.
- [ ] 예전 `deep_analysis` stub을 독립 queue로 등록하거나 답변별 Turn job을 임의 추가하지 않는다.
- [ ] job payload에는 작은 식별자만 넣고 worker가 PostgreSQL 원본을 다시 조회한다.
- [ ] 외부 호출 전후 current status, SHA, prompt version, Turn과 입력 fingerprint를 비교한다.
- [ ] stale 결과, 종료 후 질문 결과와 범위가 바뀐 분석 결과를 현재 상태에 저장하지 않는다.
- [ ] DB commit 뒤 Redis mirror와 알림을 갱신하며 Redis를 영구 원본으로 취급하지 않는다.
- [ ] 저장 뒤 알림만 실패하면 기존 결과를 재전달하고 모델을 다시 호출하지 않는다.
- [ ] Redis lock만으로 중복 방지를 완료했다고 하지 않고 AI-L12의 durable 기준을 적용한다.
- [ ] 텍스트 WS의 기존 answer와 서버 이벤트를 유지하고 내부 AI 객체를 그대로 노출하지 않는다.
- [ ] `answerReceived`의 저장 완료 의미는 FE 소비자 요구로 검수하고 AI-L13에서 BE·FE가
  채택한 뒤 적용한다. 채택한 경우에도 다음 질문 허용 의미와 구분한다.
- [ ] 현재 wire에 없는 Turn ID·제출 ID·종료 메시지·reconnect payload를 임의 추가하지 않는다.
- [ ] report lazy 200/202/409와 profile 후속 enqueue를 유지하되 AI-L15~L17 보류를 숨기지 않는다.
- [ ] public snake_case/camelCase 변환과 required/null 검증은 BE schema 계층에서 수행한다.
- [ ] 코드와 문서를 연결했다는 이유로 실제 DB·Redis·WS·worker·provider 검증 완료를 주장하지 않는다.

## 검증

추가 예정, 현재 없음: `backend/tests/agents/test_ai_integration.py`.
Workflow별 추가 예정, 현재 없음: `backend/tests/features/` 아래 해당 기능 통합 테스트.

- [ ] adapter가 승인된 입력만 전달하고 typed 성공·실패를 service에 반환하는지 검사한다.
- [ ] fake provider로 성공, timeout, parse/schema 실패와 1회 재시도 소유권을 검사한다.
- [ ] Wanted 변환과 profile 집계 경로에서 LLM client가 호출되지 않는지 검사한다.
- [ ] 여섯 FIX job의 등록·enqueue를 검사하고 old stub 이름이 새 queue가 되지 않는지 확인한다.
- [ ] PostgreSQL로 중복 job, stale result, 저장 뒤 알림 실패와 종료 중 완료를 검사한다.
- [ ] Redis snapshot hit/miss/expiry/손상 시 PostgreSQL 재구성을 검사한다.
- [ ] WS answer 저장부터 평가·Director·질문 commit·전달 순서와 중복 차단을 검사한다.
- [ ] report 생성과 profile 실패 독립성, 200/202/409의 승인된 범위를 검사한다.
- [ ] 공개 serializer는 공통 계약의 필드만 내보내며 내부 raw output·결정 객체를 숨긴다.
- [ ] 실제 provider와 서비스 검증은 mock 결과와 별도 실행·보고한다.

## 완료 조건

- [ ] AI package와 BE 사이에 승인된 typed adapter만 존재하고 역의존이 생기지 않는다.
- [ ] prompt/config, provider I/O, DB·Redis, ARQ, WS와 공개 변환의 BE 소유권이 유지된다.
- [ ] task별 독립 검사와 PostgreSQL·Redis·worker·WS 통합 검사가 구분되어 통과한다.
- [ ] 멱등성·stale 결과·부분 실패가 빈 성공이나 중복 저장으로 바뀌지 않는다.
- [ ] 미결정 gate가 있는 공개 흐름은 완료로 표시하지 않는다.

## 결정 대기와 재개 조건

| 항목 | 지금 가능한 작업 | production 연결 재개 조건 |
| --- | --- | --- |
| AI-L01·L02·L04 | provider 독립 adapter와 실패 fixture | 실제 model, 내부 계약, 실행 상한·attempt 책임 승인 |
| AI-L05·L06·L07 | 단계별 입력·부분 실패·근거 fixture | JD 순서, L2 준비 기준, 추천 산식·미계산 표시 합의 |
| AI-L11 | 기존 job별 함수·enqueue 검사 | signature, payload, timeout, Turn job 여부 확정 |
| AI-L12 | 중복·stale·알림 실패 시나리오 | transaction, durable key/lock, 복구·outbox 결정 |
| AI-L13·L14 | FIX 메시지 내부 처리 fixture | WS 경로·인증·종료·제출 식별·reconnect 계약 확정 |
| AI-L15·L16 | narrative와 생성 시나리오 | 점수 공개 계약, 생성 가능 상태·attempt 정책 확정 |
| AI-L17 | 완료 면접 입력 집계 mock | profile 중복 제거·job 인수·저장·실패 정책 확정 |

대기 항목의 현재 상태는 [later.md](../../later.md)에서 확인하고, 각 gate를 해결한 범위만
통합한다. 하나의 보류를 이유로 독립 mock·adapter 검토까지 모두 중단하지 않는다.
