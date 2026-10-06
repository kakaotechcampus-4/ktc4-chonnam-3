# 0010 Sprint 1 인터페이스와 런타임 보류 해소

> 후속 안내(2026-09-22): 아래 `accessToken` 인증 부분은 [공통 0003](../../shared/decisions/0003-sprint1-session-auth.md)의 Redis·`devon_session` 세션으로 대체됐다. JWT는 Sprint 2로 이관하며 나머지 인터페이스·런타임 결정은 유지한다. 본문은 당시 결정 이력으로 보존한다.

상태: Partially Superseded — 인증 쿠키 부분만 공통 0003으로 대체
날짜: 2026-09-15  
관련 PR: 미기록  
검토자: 팀 기획 최종 검토

## 맥락

작성 당시 `later.md`에 남아 있던 Sprint 1 구현 전 보류 중 일부가 FE·BE·AI 계약을 막고 있었다. 주요 대상은 리포트 점수, WebSocket 식별자와 메시지, 준비 실패 retry, 문서 preview, JD 신호와 분석 단계, L2 partial success, LLM attempt, ARQ retry, lazy report, profile summary, worker 분리 정책이다.

## 결정

### 리포트 점수

- Sprint 1 리포트 200 응답에는 점수가 반드시 있다.
- `totalScore`와 `scores[].score`는 0~100 number다.
- score key는 `project_understanding`, `technical_reasoning`, `problem_solving`, `communication`, `contribution_clarity`, `company_job_fit` 6개를 유지한다.
- `totalScore`는 6개 항목 score의 단순 평균이다.
- 가중치, nullable score, status 기반 미계산 표현은 Sprint 1에 사용하지 않는다.
- 항목별 세부 기준은 평가 담당자가 보강할 수 있으며 `score_criteria` seed/version 갱신으로 반영한다.

### WebSocket과 준비 흐름

- REST route와 화면 영구 식별자는 `interviewId`를 사용한다.
- WS는 realtime `sessionId` 기준 `/api/ws/interviews/{sessionId}`를 사용한다.
- `POST /interviews`와 `GET /interviews/{id}`는 `sessionId`를 응답에 포함한다.
- WS 인증은 HttpOnly `accessToken` cookie handshake로 처리한다. query/body/subprotocol token은 사용하지 않는다.
- Sprint 1 텍스트 WS에서 `questionEnd`는 제거한다. `question` 이벤트가 질문 전달 완료를 의미한다.
- client answer message는 `{ "type": "answer", "turn": number, "text": string }`다.
- `answerReceived`는 답변 수신·저장 완료 신호다. 입력 제출 상태는 해제하되, 새 답변 입력은 다음 `question`이 올 때까지 열지 않는다.
- 준비 실패 재시도는 WS 메시지가 아니라 `POST /interviews/{id}/prepare/retry` REST endpoint로 처리한다.
- 준비 단계 순서는 `analyze_repo -> build_persona -> set_criteria -> compose_question`이다.
- `GET /interviews/{id}`는 `answerMode`, `prepareSteps`, `lastError`, `turns`, `sessionId`를 통해 새로고침·재연결을 복구할 수 있어야 한다.

### abandoned와 reconnect

- Sprint 1에서는 연결 끊김, 새로고침, 재연결 실패만으로 `abandoned`로 전환하지 않는다.
- `abandoned`는 명시적 이탈 확인 또는 레포 재선택으로 새 세션을 만들 때만 설정한다.
- heartbeat/timeout 기반 자동 abandoned 판정은 Sprint 2로 넘긴다.

### 문서 preview

- Sprint 1의 `/documents/preview`는 포트폴리오 전용으로 사용한다.
- 자소서는 Sprint 1에서 preview POST 대상이 아니다.
- `POST /analysis-runs.documentId`는 단일 필드를 유지하며 의미는 portfolio preview document ID다.
- preview에서 사용하는 핵심 신호는 포트폴리오 GitHub URL이다.
- 문서 claim 추출과 자소서 기반 claim 활용은 Sprint 2로 넘긴다.

### JD 신호와 추천 단계

- 외부 분석 7단계 순서는 `doc_extract -> repo_select -> repo_detail -> jd_fetch -> jd_extract -> repo_analyze -> match_score`로 유지한다.
- 첫 batch의 `repo_select`는 JD가 준비되기 전이므로 `jd_signal`을 사용하지 않는다.
- 첫 batch candidate source는 `portfolio_mentioned`, `base_rank_top`, `high_contribution`, `other`만 사용한다.
- JD 기반 match score와 recommend reason은 `match_score` 단계와 후속 candidate page에서만 사용한다.

### L2 partial success와 context limitations

- primary repo 1~2개 중 최소 1개 repo에 검증된 notable area가 1개 이상 있으면 면접 준비 성공을 허용한다.
- 검증된 notable area가 총 0개면 `preparing_failed`다.
- 무효 repo/path/area는 질문 근거에서 제외하고 내부 context limitations에 남긴다.
- Director와 report는 limitations에 포함된 미관찰 범위를 관찰 사실처럼 질문하거나 평가하지 않는다.
- Sprint 1 FE에는 상세 limitations를 공개하지 않고 준비 성공/실패만 노출한다.

### LLM attempt와 worker retry

- LLM attempt는 공통 LLM gateway/task 호출 계층에서만 관리한다.
- timeout·재시도 가능한 provider 오류·parse/schema 실패는 함수 내부에서 최대 1회 재호출하며 총 2회까지만 호출한다. 2026-09-23 PR #56 리뷰 보완으로 영구 HTTP 요청 오류·quota 소진은 provider 실패로 즉시 종료하고, 일시적 제한의 대기는 요청 timeout 이내로 제한한다. 상태별 분류·Retry-After·호출분 metadata는 [내부 호출 계약](../contracts.md#model-gateway와-실패)의 현행 규칙을 따른다.
- semantic 실패는 재호출하지 않는다.
- SDK/provider 자체 retry는 호출 수가 곱해지지 않게 끄거나 최소화한다.
- ARQ 자동 retry는 Sprint 1에서 사용하지 않고 `max_tries=1`로 둔다.
- `analysis_jobs.retry_count`는 사용자 수동 retry 횟수만 의미하며 ARQ retry와 섞지 않는다.
- reaper는 `queued`인데 큐에 없는 작업만 다시 enqueue한다. `running` worker lost 자동 재실행은 Sprint 1에 하지 않는다.

### Lazy report와 profile summary

- report 생성 가능 조건은 `interview.status === 'completed'`이고 답변 완료 turn이 1개 이상인 경우다.
- `abandoned`, `preparing`, `preparing_failed`, `in_progress`는 report 생성 대상이 아니다.
- 이미 생성된 report는 200으로 반환한다.
- report가 없고 생성 가능하며 생성 실패 이력이 없으면 `report_generate`를 enqueue하고 202를 반환한다.
- 생성 중이면 중복 enqueue 없이 202를 반환한다.
- 생성 실패 이력이 있으면 자동 재생성하지 않고 `409 report_unavailable`로 닫는다.
- report 재생성, 수동 재시도, 이의제기 기반 재평가는 Sprint 2다.
- `profile_summary`는 report 성공 뒤 enqueue하되 report 응답을 막지 않는다. 실패 재시도·복구·상세 실패 처리는 Sprint 2다.

### Worker 분리

- Sprint 1은 기본 queue 1개와 단일 ARQ worker 프로세스에 기존 6개 job을 등록한다.
- job 함수는 논리적으로 분리한다.
- Sprint 1에서 job별 `queued_at`, `started_at`, `completed_at`, `duration_ms`, `queue_wait_ms`, `job_type`, `status`, `error_code`를 수집해 Sprint 2 worker/queue 분리 여부를 판단한다.

## 영향

- 당시 `later.md`에서 확정된 부분을 제거하거나 남은 질문만 좁히기로 했다.
- FE 문서의 `prepareRetry` WS 메시지, `questionEnd`, 자소서 preview 설명은 Sprint 1 기준으로 정정한다.
- BE/AI 문서의 ARQ retry, report 재생성, profile 실패 복구, JD signal, L2 readiness 문구를 이 결정에 맞춘다.
- 이 결정은 실제 provider/model ID, 내부 JSONB 저장 계약, task별 timeout/token/context/tool budget, Evidence 디렉터리 열거 상한, profile 집계 중복 제거 정책까지 승인하지 않는다.

## 대체 관계

- AI-L04, AI-L05, AI-L06, AI-L11, AI-L13, AI-L14, AI-L15, AI-L16, AI-L17의 일부 보류를 해소한다.
- AI-L01, AI-L02, AI-L07, AI-L08, AI-L09, AI-L10, AI-L18 이후 항목은 당시 `later.md`에서 후속 관리하기로 했다. 현재 후속 결정은 [결정 목록](README.md), 미완료 작업은 [구현·검수 인계표](../../../ai/docs/pipeline.md#기존-id별-구현검수-인계), Sprint 2 항목은 [착수 시 검토할 사항](../features/extensions.md#sprint-2-착수-시-검토할-사항)에서 확인한다.
