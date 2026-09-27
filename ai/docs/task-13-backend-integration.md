# task-13 - Backend 통합과 인계

상태: 구현 가이드. AI package 설치 smoke, 공통 호출·Director 질문 경로의 HTTP adapter 검사가 존재한다. 실제 면접 service·저장·WS 연결은 미구현이다.

## 목표

검증된 AI callable을 기존 BE API·pipeline·worker·텍스트 WS에 연결한다. 이 작업은
[task-06 입력 준비](task-06-context-preparation.md)의 readiness 조정과 다르다. task-06은
호출 가능한 입력을 준비하고, task-13은 승인된 계약을 실제 I/O·상태·저장 흐름에 인계한다.

전체 순서와 task별 연결 전 검사는 [AI 구현 파이프라인](pipeline.md)을 따른다. 관련 AI 작업은
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
  profile 통계 집계 비호출 원칙을 지키며 개인 역할 요약은 후속 [0019](../../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)의 LLM 사용을 따른다.
- [0018 기존안 일괄 채택](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)과 [구현·검수 인계](pipeline.md#기존-id별-구현검수-인계)에 따라 기존 결정은 유지하고 실제 연결을 검증한다.

## 선행 조건

- [ ] 연결할 AI task의 callable, typed 성공·실패와 의미 검증이 독립 테스트를 통과한다.
- [ ] task별 채택한 계약과 BE 변환·저장 위치를 기존 경계에 맞춰 구현한다.
- [ ] 선택한 provider/model과 prompt/config 조회를 실제 연결·검증한다.
- [ ] timeout·token·Tool 상한을 운영 조건과 측정에 따라 설정하고 기존 공통 재시도·attempt 책임을 유지한다.
- [ ] 해당 흐름의 구현·검수 인계 항목을 검사하고 아직 실행하지 않은 범위는 구분한다.
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
- [ ] `profile_summary`는 report 성공 뒤 실행하며 통계는 기존 자료로 집계하고 개인 역할만 LLM으로 요약한다. job·저장·갱신과 실패 분리는 유지한다.
- [ ] 프로필은 [0016 결정](../../spec/ai/decisions/0016-profile-language-aggregation.md)에 따라 같은 저장소를 한 번만 세고 언어 비율을 저장소별 동일 비중으로 평균낸다. 기존 저장 자료 연결·누락 처리와 공개 필드 유지를 확인한다.
- [ ] Sprint 1 roleSummary에 0019의 역할 요약을 기존 문자열로 전달하고, 모델 결과가 입력 근거를 넘는 개인 기여를 만들지 않는지 확인한다. 일괄 기능 보류 안내를 정상 응답 기준으로 사용하지 않는다.
- [ ] 추천은 [0017](../../spec/ai/decisions/0017-recommendation-score-deferral.md)·[0018](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)에 따라 matchScore=null과 직접 기술 비교를 사용한다. 관련 근거가 있는 후보를 기존 run 후보 순서에서 run 전체 최대 5개 추천하고, 태그 겹침을 개별 요구사항 충족으로 단정하지 않는다.
- [ ] 현재 FIX job은 `initial_sync`, `analysis_run`, `candidate_page_analyze`, `interview_prep`,
  `report_generate`, `profile_summary` 여섯 개임을 기준으로 등록과 enqueue를 검사한다.
- [ ] 예전 `deep_analysis` stub을 독립 queue로 등록하거나 답변별 Turn job을 임의 추가하지 않는다.
- [ ] job payload에는 작은 식별자만 넣고 worker가 PostgreSQL 원본을 다시 조회한다.
- [ ] 외부 호출 전후 current status, SHA, prompt version, Turn과 입력 fingerprint를 비교한다.
- [ ] stale 결과, 종료 후 질문 결과와 범위가 바뀐 분석 결과를 현재 상태에 저장하지 않는다.
- [ ] DB commit 뒤 Redis mirror와 알림을 갱신하며 Redis를 영구 원본으로 취급하지 않는다.
- [ ] 저장 뒤 알림만 실패하면 기존 결과를 재전달하고 모델을 다시 호출하지 않는다.
- [ ] Redis lock만으로 중복 방지를 완료했다고 하지 않고 기존 식별자·DB 상태·중복 제약을 확인한다. 새 outbox·running 작업 자동 재실행은 추가하지 않는다.
- [ ] 텍스트 WS의 기존 answer와 서버 이벤트를 유지하고 내부 AI 객체를 그대로 노출하지 않는다.
- [ ] 이미 채택한 `answerReceived`의 답변 저장 완료 의미를 실제 송수신에서 검사하고 다음 질문 허용 의미와 구분한다.
- [ ] 현재 wire에 없는 Turn ID·제출 ID·종료 메시지·reconnect payload를 임의 추가하지 않는다.
- [ ] report lazy 200/202/409·기존 6개 0~100 점수와 단순 평균·profile 후속 enqueue를 유지하며 실제 seed 검수와 저장·응답 연결을 확인한다.
- [ ] public snake_case/camelCase 변환과 required/null 검증은 BE schema 계층에서 수행한다.
- [ ] 코드와 문서를 연결했다는 이유로 실제 DB·Redis·WS·worker·provider 검증 완료를 주장하지 않는다.

## 검증

추가 예정, 현재 없음: `backend/tests/agents/test_ai_integration.py`.
Workflow별 추가 예정, 현재 없음: `backend/tests/features/` 아래 해당 기능 통합 테스트.

- [ ] adapter가 승인된 입력만 전달하고 typed 성공·실패를 service에 반환하는지 검사한다.
- [ ] fake provider로 성공, timeout, parse/schema 실패와 1회 재시도 소유권을 검사한다.
- [ ] Wanted 변환·프로필 통계 계산의 LLM 비호출과 개인 역할 요약의 기존 LLM 호출·검증 연결을 각각 검사한다.
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
- [ ] 미검증 통합 흐름과 확정 자료 정책의 실제 적용이 검증되지 않은 원문 운영을 완료로 표시하지 않는다.

## 구현·검수 인계

| 항목 | 독립 작업 | 실제 연결 전 확인 |
| --- | --- | --- |
| AI-L01·L02·L04 | provider 독립 adapter와 실패 fixture | 선택 모델·기존 내부 계약·재시도 책임의 연결, 운영 상한 설정과 측정 |
| AI-L06·L07 | 채택한 부분 실패·직접 기술 비교·추천 null fixture | L2 실제 지원 범위, 기존 순서의 run 전체 최대 5개 추천·실제 근거·저장 연결 |
| AI-L11 | 기존 6개 job별 함수·enqueue 검사 | 채택한 식별자 payload·DB 재조회·단일 worker 연결, 운영 timeout 검사. 별도 Turn job 없음 |
| AI-L12 | 중복·stale·알림 실패 시나리오 | 기존 T3/T4·짧은 transaction·행 잠금/조건부 갱신·중복 제약·queued 재등록 범위의 장애 검사 |
| AI-L13·L14 | FIX 메시지 내부 처리 fixture | 기존 WS 경로·인증·저장 완료 신호·명시적 이탈 의미 유지, 종료 wire와 재연결의 실제 송수신 검사 |
| AI-L15·L16 | narrative와 기존 생성 시나리오 | 기존 6개 0~100 점수·평균의 세부 seed 검수, 성공본 재사용·실패 시 409·재생성 없음의 연결 |
| 프로필 — AI-L17 결정 해소 | 채택한 중복 제거·언어 비율 평균·0019 역할 요약 근거 검증 mock | 기존 저장 필드·LLM 역할 요약·갱신·응답의 실제 구현과 검증 |

[0018](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)과 [작업 지도](pipeline.md#기존-id별-구현검수-인계)를 따른다. 위 항목은 같은 설계를 사용자에게 다시 묻는 목록이 아니다. 자료 정책은 0018의 보관 유지 결정을 적용하며 실제 연결 완료 여부는 구현·검수 증거로 구분한다. 하나의 미검증 경로 때문에 독립 mock·adapter 검토까지 모두 중단하지 않는다.
