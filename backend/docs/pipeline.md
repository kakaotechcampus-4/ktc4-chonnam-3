# 비동기 파이프라인

상태: Sprint 1 FIX.

## Queue

ARQ + Redis를 사용한다. `BackgroundTasks`는 재시작 시 유실되고, Celery는 현재 FastAPI async 코드와 운영 부담이 크다.

등록 작업:

| task | 목적 |
| --- | --- |
| `initial_sync` | GitHub OAuth 직후 public repo L0-a 수집 |
| `analysis_run` | 7 step 분석 run |
| `candidate_page_analyze` | 추가 후보 page의 L0-b/L1 분석 |
| `interview_prep` | 면접 준비, L2, Redis context snapshot, 첫 질문 |
| `report_generate` | lazy report 생성 |
| `profile_summary` | report 성공 후 사용자 프로필 요약 갱신 |

LLM 실패는 자동 1회 재시도한다. 구조화 JSON parsing 실패도 1회 재시도 후 실패 처리하고 raw output을 저장한다.

## Analysis Run

```text
POST /analysis-runs
  -> postingUrl 검증
  -> optional documentId 검증
  -> 동일 fingerprint queued/running 재사용
  -> analysis_jobs queued
  -> analysis_run enqueue

analysis_run
  -> doc_extract
  -> repo_select
  -> repo_detail
  -> jd_fetch
  -> jd_extract
  -> repo_analyze
  -> match_score
  -> succeeded / partial / failed
```

진행 상태 update 순서:

1. Postgres `analysis_jobs.steps`, `status`, `progress`
2. Redis mirror
3. Pub/Sub publish

SSE가 먼저 완료를 받고 DB가 아직 running인 상태를 막기 위해 이 순서를 지킨다.

## Candidate Page

`GET /analysis-runs/{runId}/candidates?page=N`

- 분석 완료 page면 `200`.
- 미분석 page면 `analysis_repo_candidate_pages` upsert 후 `candidate_page_analyze` enqueue, `202 analyzing`.
- page job은 전체 run status를 변경하지 않는다.

## Interview Prep

`POST /interviews` 성공 직후 enqueue한다.

```text
interview_prep
  -> primary repo 1~2개 선정
  -> L2 deep analysis
  -> notable_areas 검증
  -> context_state 초기화
  -> Redis interview context snapshot 생성
  -> 첫 hr_manager 질문 생성
```

준비 실패는 `preparing_failed`다. 사용자 이탈인 `abandoned`와 섞지 않는다.

## Text WebSocket

Sprint 1은 텍스트-only다.

클라이언트 -> 서버:

```json
{ "type": "answer", "text": "..." }
```

서버 -> 클라이언트:

- `answerReceived`
- `thinking`
- `evidenceCheck`
- `question`
- `interviewEnd`
- `error`

오디오, STT, TTS, transcript는 Sprint 2.

## Turn Loop

```text
T1 question insert
T2 answer update
T3 answer analysis + optional Evidence Retriever
T4 Director decision + context_state update + Redis snapshot update
```

질문 근거(`question_basis`)와 평가 근거(`evaluation_basis`)를 분리한다. `answer_vs_code` 충돌이 발견되면 `evidence_conflicts`를 남기고 다음 꼬리질문 후보로 사용한다.

## Report

리포트는 lazy generation이다.

```text
GET /interviews/{id}/report
  -> report exists: 200
  -> generating lock exists: 202
  -> generation possible: enqueue report_generate, 202
  -> unavailable: 409 report_unavailable

report_generate succeeded
  -> enqueue profile_summary
```
