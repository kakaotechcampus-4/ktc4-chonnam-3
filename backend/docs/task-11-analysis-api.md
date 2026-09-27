# task-11 — 분석 API · 큐 배선

> 선행: task-08, task-09, task-10
> 근거: `spec/backend/features/analysis-run.md`

## 목표

분석 run 생성, 상태 조회, 결과 조회, candidate page API를 구현한다.

## 작업

- `POST /analysis-runs`는 `postingUrl` 필수, `documentId` optional.
- 새 run 생성은 `202 {"runId": "..."}`를 반환한다. 동일 fingerprint의 queued/running job은 새로 만들지 않고 `409 run_in_progress`와 `error.details.runId`로 기존 run ID를 반환한다.
- 종료된 job은 새 run을 허용한다.
- `GET /analysis-runs/{runId}`는 FE `RunStatus`로 매핑한다.
- `GET /analysis-runs/{runId}/result`는 partial run도 조회 가능하게 한다.
- `GET /analysis-runs/{runId}/candidates?page=N`은 완료 page 200, 미분석 page 202를 반환한다.
- candidate page 분석은 ARQ job으로 넘긴다.

## 완료 조건

- 동일 fingerprint의 중복 생성 409·기존 run ID, partial->failed 매핑, result 조회 가능 조건을 테스트한다.
- 후보 page 중복 enqueue가 방지된다.
