# 비동기 파이프라인 · SSE · WebSocket

## 1. 큐 — ARQ

| 후보              | 판단                                                                              |
| ----------------- | --------------------------------------------------------------------------------- |
| `BackgroundTasks` | API 프로세스와 생명주기 공유 → 재시작 시 run 유실, 4-2-v2 가 영구 `running`       |
| Celery            | 동작하지만 sync 기반. `httpx`/LLM async 코드와 섞으면 이벤트 루프 관리가 늘어난다 |
| **ARQ**           | asyncio 네이티브 + Redis 만 요구. 이미 Redis 가 확정 스택이라 인프라 추가가 0     |

`app/workers/arq_app.py` 의 `WorkerSettings` 에 작업별 타임아웃과 `job_timeout` 을 둔다. Sprint 1에서 ARQ 자동 retry는 사용하지 않으므로 `max_tries=1`로 둔다.

`analysis_jobs.retry_count` 는 ARQ 재시도와 별개로 **사용자가 누른 재시도** 횟수다. 섞지 않는다.

등록 태스크 6종.

| 태스크                   | job_type                 | 시점                                   |
| ------------------------ | ------------------------ | -------------------------------------- |
| `initial_sync`           | `initial_sync`           | M1 — 후속 동기화 시작점에서 실행; OAuth callback에서는 enqueue하지 않음 |
| `analysis_run`           | `analysis_run`           | M2 — 공고 입력 후 7단계 분석           |
| `candidate_page_analyze` | `candidate_page_analyze` | M3 — 추천 후보 더 보기 page 분석       |
| `interview_prep`         | `interview_prep`         | M4-a — 면접 준비                       |
| `report_generate`        | —                        | M6 — lazy report 생성                  |
| `profile_summary`        | —                        | report 생성 성공 후 사용자 프로필 집계 |

Sprint 1에서는 기본 queue 1개와 단일 ARQ worker 프로세스에 위 6개 job을 모두 등록한다. worker/queue 물리 분리는 Sprint 1 운영 지표를 보고 Sprint 2에서 판단한다. 각 job은 `queued_at`, `started_at`, `completed_at`, `duration_ms`, `queue_wait_ms`, `job_type`, `status`, `error_code`를 남긴다.

## 2. run 실행 흐름

```
POST /analysis-runs (application/json)
  ├ 검증: postingUrl 필수(400 posting_url_required), Wanted URL 여부
  ├ optional documentId 검증  # Sprint 1에서는 portfolio preview documentId
  ├ Redis SETNX run:lock:{userId}:{jobType}  ─┐ 둘 중 하나라도 걸리면
  ├ INSERT analysis_jobs (queued)             ─┘ 409 run_in_progress + 진행 중 runId
  ├ documentId가 있으면 preview 결과를 analysis context에 연결
  ├ arq.enqueue('analysis_run', run_id)
  └ 202 + Location + {"runId": ...}

worker: analysis_run
  for step in [doc_extract, repo_select, repo_detail,
               jd_fetch, jd_extract, repo_analyze, match_score]:
      emit(step, 'running')     # ① UPDATE + COMMIT  ② Redis HSET  ③ PUBLISH
      ...작업...
      emit(step, 'completed')
  UPDATE status='succeeded' + COMMIT ; PUBLISH {"type":"completed"}
  실패 시: UPDATE status='failed', error_code=? + COMMIT ; PUBLISH {"type":"failed","reason":...}
```

### `emit()` 의 커밋 경계

⚠ **`emit()` 은 Postgres 커밋 완료 → Redis → PUBLISH 순서를 지킨다.** `UPDATE` 실행이 아니라
**커밋**이 기준이다.

| 순서                     | 결과                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| 커밋 **전**에 PUBLISH    | SSE 로 `completed` 를 받은 클라이언트가 `GET /analysis-runs/{runId}` 에서 아직 `running` 을 본다. 화면에 "완료" 가 떴는데 결과가 없다 |
| 커밋 **후**에 Redis 실패 | Redis 스냅샷에 이전 상태가 남는다. **job 은 실패시키지 않고 로그만 남긴다**                                                           |

두 번째를 감수하는 근거는 [redis-keys.md](redis-keys.md) 의 원칙이다 — **진실은 Postgres,
Redis 는 미러.** Redis 갱신 실패는 표시 지연이지 데이터 손실이 아니다. 3절의 SSE 초기 상태를
Postgres 에서 읽는 것이 이 실패에 대한 복구 경로다.

### 락 키에 `jobType` 이 들어가는 이유

M1 `initial_sync`는 후속 동기화 기능이 명시적으로 시작한다. 현재 OAuth callback은 로그인만 완료하고 enqueue하지 않는다. 사용자가 동기화와 함께 공고를 입력하면 M2와 겹칠 수 있는데,
사용자 단일 락으로 두면 **정상 흐름이 `run_in_progress` 로 막힌다.**
DB 부분 유니크도 `(user_id, job_type) WHERE status IN ('queued','running')` 이다.

### DB 는 썼는데 큐에 못 넣으면 — reaper

`INSERT analysis_jobs` 와 `arq.enqueue` 는 **서로 다른 저장소에 연달아 쓰는 것(dual-write)** 이다.
둘 다 성공하거나 둘 다 실패하는 것을 보장할 방법이 없다. 사이에서 죽으면:

```
INSERT analysis_jobs (queued)   ✓ 커밋됨
arq.enqueue(...)                ✗ 네트워크 장애 · 인스턴스 종료
```

- 워커가 영영 집어가지 않는다 → 4-2-v2 진행바가 멈춘 채로 남는다
- 사용자가 새로 시도해도 **API 의 `INSERT` 가 부분 유니크 인덱스에 막혀 `409 run_in_progress`**
  가 된다 (`(user_id, job_type) WHERE status IN ('queued','running')`)

⚠ **막히는 주체는 워커가 아니라 API 다.** 유니크 인덱스는 Postgres 제약이라 Redis · 워커와
무관하고, 새 요청은 enqueue 단계까지 가지도 못한다.

**reaper로 푼다.** 주기적으로 `analysis_jobs`와 큐 상태를 대조해 `queued`인데 큐에 없는
작업을 다시 등록한다. 4.3절과 같이 이 주기 작업은 분석 reaper만 담당하며,
Sprint 1에는 `abandoned` 자동 판정 cron을 추가하지 않는다.

### 중복 실행을 막는 3중 방어

ARQ 는 **at-least-once** 다. 워커가 작업 도중 죽으면 같은 job 이 다시 실행될 수 있고, reaper 의
재등록도 중복 가능성을 만든다. **중복을 0으로 만드는 것이 아니라 중복돼도 안전한 것**이 목표다.

| 계층        | 방법                                                        | 막는 것                                |
| ----------- | ----------------------------------------------------------- | -------------------------------------- |
| 큐          | `arq.enqueue(..., _job_id=f"{job_type}:{run_id}")`          | 같은 run 이 큐에 두 번 들어가는 것     |
| 태스크 진입 | `analysis_jobs.status` 확인 → 이미 `running` 이면 즉시 종료 | 살아 있는 워커와의 충돌                |
| DB          | `repo_analyses` UNIQUE + `ON CONFLICT DO NOTHING`           | 두 워커가 같은 결과를 중복 저장하는 것 |

세 번째의 `UNIQUE (repository_id, analysis_level, head_sha, prompt_version)` 가 **자연 멱등 키**다.
중복 실행돼도 LLM 비용만 낭비되고 데이터는 깨지지 않는다.

Sprint 1에서는 `running` 으로 남은 행이 worker lost로 의심되더라도 자동 재실행하지 않는다.
자동 재실행을 넣으면 이전 worker 결과와 새 worker 결과의 충돌 처리가 필요하므로, 해당 작업은
실패 상태로 닫고 재실행·복구 정책은 Sprint 2에서 다룬다.

> 1절의 `analysis_jobs.retry_count` 는 여기서 말하는 재시도가 아니다. ARQ 재시도 · reaper 재등록과
> 별개로 **사용자가 누른 재시도** 횟수다. 섞지 않는다.

### 일부 실패와 전체 실패를 구분한다

후보 중 일부만 실패하면 `analysis_jobs.status='partial'`, 전부 실패하면 `failed`다.
FE에는 두 상태 모두 `failed`로 매핑하지만 부분 결과는 조회할 수 있다. 상세 기준은
[분석 Run](../../spec/backend/features/analysis-run.md)의 부분 실패 계약을 따른다.

## 2.1 Candidate Page

`GET /analysis-runs/{runId}/candidates?page=N`

- 분석 완료 page면 `200` 으로 repo card page를 반환한다.
- 미분석 page면 `analysis_repo_candidate_pages` upsert 후 `candidate_page_analyze` 를 enqueue하고
  `202 { "status": "analyzing", "retryAfter": 3 }` 을 반환한다.
- page job은 전체 run status를 변경하지 않는다.

## 2.2 Interview Prep

`POST /interviews` 성공 직후 `interview_prep` 을 enqueue한다.

```text
interview_prep
  -> primary repo 1~2개 선정
  -> L2 deep analysis
  -> notable_areas 검증
  -> context_state 초기화
  -> Redis interview context snapshot 생성
  -> 첫 hr_manager 질문 생성
```

준비 실패는 `preparing_failed` 다. 사용자 이탈인 `abandoned` 와 섞지 않는다.

## 3. SSE

`sse-starlette` + `realtime/bus.py`. 접속 시 순서:

1. `run:{runId}:events` 를 **먼저 구독하고, 구독이 실제로 성립한 것을 확인한다**
2. 그다음 **Postgres** 에서 현재 step 상태를 읽어 흘려보낸다
3. 이미 종료된 run 이면 `completed` / `failed` 하나 보내고 스트림을 닫는다
4. 구독 이후 들어온 이벤트를 이어서 흘려보낸다 — step 단위로 중복을 제거한다

⚠ **구독이 먼저다.** 반대로 하면 상태를 읽은 뒤 구독하기 전 사이에 run 이 끝났을 때
`completed` 를 영영 못 받는다.

```
(뒤집힌 순서 — 이렇게 하면 안 된다)
  스냅샷 읽음  → "repo_analyze 진행 중"
       ↓ (이 틈에)
  워커 완료    → PUBLISH "completed"    구독 전이라 아무도 못 받는다
  구독 시작    → 이미 지나간 방송
→ 진행바가 6/7 에서 멈춘 채 남는다
```

마지막 step(`match_score`)이 순식간에 끝나는 구조라 이 틈에 빠질 확률이 낮지 않다.

순서를 뒤집으면 구독 직후 이벤트와 스냅샷이 겹칠 수 있다. **step 단위 중복 제거**로 처리한다 —
같은 step 의 같은 상태는 한 번만 내보낸다.

⚠ **초기 상태는 Redis 가 아니라 Postgres 에서 읽는다.** 2절의 커밋 경계에서 "커밋 후 Redis 갱신
실패" 를 감수하기로 했으므로, `run:{runId}:steps` 에는 이전 상태가 남아 있을 수 있다.
`GET /analysis-runs/{runId}` 도 같은 이유로 Postgres 를 본다. Redis 스냅샷은 실측에서 조회 부하가
문제가 될 때 도입한다(미결).

Pub/Sub 은 **at-most-once** 라 구독 이후에도 유실이 가능하다. 종료 상태를 확인할 때까지
Postgres 를 주기적으로 재확인하는 폴백을 둔다. 이벤트 보관과 재생까지 필요해지면 Redis Streams
전환을 검토한다(미결).

`estimatedSeconds` 는 `analysis_jobs.estimated_seconds`. 초기값은 상수(20), 이후 완료 run 의
소요시간 중앙값으로 갱신한다.

SSE는 프록시·CDN에서 버퍼링되지 않아야 한다. 현재 Caddy의 API 라우트에는 FE용 압축·캐시를
섞지 않고, 추후 CloudFront를 사용하면 해당 behavior의 자동 압축을 끈다
([deploy.md](deploy.md) 3절 ③). `Cache-Control: no-store`와 15초 keep-alive 코멘트(`: ping`)를
사용하며 `X-Accel-Buffering: no`의 적용 여부는 실제 프록시 종류에 맞춰 확인한다.

---

## 4. WebSocket 면접

`GET (Upgrade) /ws/interviews/{sessionId}` — `features/interview/ws.py`

브라우저에서 붙는 실제 경로는 `/api/ws/interviews/{sessionId}` 다. Caddy 가 `/api/*` 를 backend 로
전달하고, FE 문서에서는 fetch 래퍼를 거치지 않는 WS 예시에 `/api` prefix 를 직접 쓴다.

**스프린트1 은 양방향 텍스트다.** 오디오 프레임 · TTS · `transcript` · `stt_failed` ·
`tts_failed` 는 스프린트2 에서 붙인다 (`interview_sessions.answer_mode` CHECK = `'text'`).
클라→서버 답변 메시지는 `{ "type": "answer", "turn": n, "text": "..." }`다. 서버는 `turn`이 현재 답변 가능한 turn과 일치하고 아직 저장된 답변이 없을 때만 저장한다.

### 4.1 핸드셰이크

```
1) 쿠키 accessToken 검증           실패 → 401 (핸드셰이크 거부, WS accept 하지 않음)
2) rt:{sessionId} 조회              없음 → 409
3) userId 일치 확인                 불일치 → 409
4) interview_sessions.status 확인   completed/abandoned → 409
5) SETNX ws:lock:{sessionId}        실패 → 409 already_connected
6) accept
```

**401/409 는 `accept()` 전에** 내야 한다. accept 후 close code 로 보내면 브라우저 쪽 구분이 어렵다.

### 4.2 메시지 ↔ DB 쓰기

| WS 메시지              | 방향 | DB / Redis                                                                                                                                                                              |
| ---------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `prepareStep` ×4       | S→C  | `interview_sessions.status='preparing'`, `context_state` 초기화                                                                                                                         |
| `prepareCompleted`     | S→C  | `status='in_progress'`, `events(session_started)`                                                                                                                                       |
| `question`             | S→C  | `INSERT interview_turns(status='asked', depth, parent_turn_no, topic_code, jd_requirement_ids, claim_ids)` + **`INSERT turn_evidences(usage='question_basis')`** + `events(turn_asked)` |
| 답변 (C→S, `{type:"answer", turn, text}`) | C→S  | turn 일치·미답변 확인 후 `UPDATE interview_turns SET answer_text, answered_at, answer_duration_sec, status='answered'` + `events(turn_answered)`                                      |
| `thinking`             | S→C  | `UPDATE interview_turns SET analysis` (AnswerAnalysis) → `SET decision` (DirectorDecision) + `context_state` 갱신                                                                       |
| `evidenceCheck`        | S→C  | **`INSERT evidences(retrieved_for_turn=n, git_ref, snippet, tool_name)`**                                                                                                               |
| (불일치 발견)          | —    | `INSERT evidence_conflicts(verdict='unresolved')` — **2차**                                                                                                                             |
| `interviewEnd`         | S→C  | `status='completed'`, `events(session_completed)`                                                                                                                                       |
| 비정상 종료            | —    | `status='abandoned'`, `abandoned_at_turn=turn_count`, `events(session_abandoned)`                                                                                                       |

`evidenceCheck` 가 화면에 뜬 순간 `evidences` 에 행이 있어야 한다. 화면에는 떴는데 행이 없으면
그건 연출이고, 서비스가 주장하는 "근거 기반" 이 데이터로 증명되지 않는다.

**`turn_evidences` INSERT 누락이 가장 조용한 버그다.** 화면은 정상으로 보이고 Eval 만 깨진다.
`turn_service.py` 에서 **질문 INSERT 와 같은 트랜잭션**으로 묶어 물리적으로 빠질 수 없게 한다.

`turn_evidences` 필수 여부는 **페르소나별로 다르다.**

| persona       | 근거 없음이 | 정상 조건                                                          |
| ------------- | ----------- | ------------------------------------------------------------------ |
| `tech_lead`   | **결함**    | `turn_evidences` 가 있어야 한다                                    |
| `domain_lead` | 정상        | `jd_requirement_ids` 가 있으면 OK (JD·업종을 근거로 묻는 페르소나) |
| `hr_manager`  | 정상        | `claim_ids` 가 있으면 OK (자소서 주장을 근거로 묻는 페르소나)      |

### 4.3 이탈 처리

WS `disconnect` 만으로 `abandoned` 를 확정하지 않는다 (새로고침·터널 끊김과 구분 불가).
Sprint 1에는 하트비트/timeout 기반 자동 abandoned 판정 배치를 두지 않는다. `abandoned`는 사용자가
이탈 확인 모달에서 명시적으로 나가거나, 레포 재선택으로 새 세션을 만들 때만 설정한다.

주기 작업은 분석 reaper만 본다.

| 대상                 | 판정                                          |
| -------------------- | --------------------------------------------- |
| `analysis_jobs`      | `queued` 인데 큐에 없음 → 재등록 (2절 reaper) |

세션 재개는 미지원이다 (`status` 에 `paused` 없음). 답변 초안 저장도 없다. 제출 1회.

### 4.4 두 개의 식별자 — `interviewId` ≠ `sessionId`

`POST /interviews` 가 둘을 같이 돌려주고 WS 는 `sessionId` 로 붙는다. DB 에는
`interview_sessions.id` 하나뿐이다.

| FE 필드       | 정체                                                                   | 저장소                          |
| ------------- | ---------------------------------------------------------------------- | ------------------------------- |
| `interviewId` | `interview_sessions.id` (UUID) — 영구 식별자. 리포트·마이페이지가 참조 | Postgres                        |
| `sessionId`   | **실시간 세션 키** — WS 연결·단일접속 락·prepare 진행 상태용 단기 토큰 | Redis `rt:{sessionId}` (TTL 2h) |

이유 두 가지. ① WS 핸드셰이크 실패 조건에 `409 already_connected` 가 있다 → 연결 단위의 짧은
수명 키가 필요하다. ② `GET /interviews/{id}` 가 `sessionId` 를 응답에 포함한다 → 새로고침 후
재연결 시 다시 받아야 하는 값이라는 뜻이다.

`rt:{sessionId}` 값에 `interviewId`, `userId` 를 담는다. Redis 가 날아가면 WS 만 끊기고 면접
기록(Postgres)은 남는다. 그때 `GET /interviews/{id}` 가 새 `sessionId` 를 발급한다.

Sprint 1에서는 FE 문서와 맞춰 WS를 `sessionId`로 유지한다.

### 4.5 세션 상태 — DB와 API 5개

| `interview_sessions.status` (DB) | FE `InterviewStatus` |
| -------------------------------- | -------------------- |
| `preparing`                      | `preparing`          |
| `preparing_failed`               | `preparing_failed`   |
| `in_progress`                    | `in_progress`        |
| `completed`                      | `completed`          |
| `abandoned`                      | `abandoned`          |

준비 단계면 `currentTurn: 0`, `turns: []`를 반환한다. `preparing_failed`일 때는 `lastError`와 `prepareSteps`로 실패 화면을 복구한다.

## 5. Report

리포트는 lazy generation이다.

```text
GET /interviews/{id}/report
  -> report exists: 200
  -> generating lock exists: 202
  -> generation possible(status=completed and answered turns >= 1 and no failed generation): enqueue report_generate, 202
  -> unavailable: 409 report_unavailable

report_generate succeeded
  -> enqueue profile_summary
```

이전 `report_generate` 실패 이력이 있으면 Sprint 1에서는 자동 재생성하지 않는다. `profile_summary` 실패는 report 결과를 실패로 되돌리지 않으며 재시도·복구 정책은 Sprint 2에서 다룬다.
