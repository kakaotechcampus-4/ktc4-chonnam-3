# 비동기 파이프라인 · SSE · WebSocket

## 1. 큐 — ARQ

| 후보 | 판단 |
|---|---|
| `BackgroundTasks` | ✗ API 프로세스와 생명주기 공유 → 재시작 시 run 유실, 4-2-v2 가 영구 `running` |
| Celery | △ 동작하지만 sync 기반. `httpx`/LLM async 코드와 섞으면 이벤트 루프 관리가 늘어난다 |
| **ARQ** | ✓ asyncio 네이티브 + Redis 만 요구. 이미 Redis 가 확정 스택이라 인프라 추가가 0 |

`app/workers/arq_app.py` 의 `WorkerSettings` — 작업별 타임아웃, `max_tries`, `job_timeout`.

⚠ `analysis_jobs.retry_count` 는 ARQ 재시도와 별개로 **사용자가 누른 재시도** 횟수다. 섞지 않는다.

등록 태스크 4종.

| 태스크 | job_type | 시점 |
|---|---|---|
| `initial_sync` | `initial_sync` | M1 — GitHub 연동 직후 백그라운드 |
| `interview_prep` | `interview_prep` | M2 — 공고 입력 후 분석 |
| `deep_analysis` | `deep_analysis` | M4-a — 면접 준비 |
| `report_generate` | — | M6 — 면접 종료 |

## 2. run 실행 흐름

```
POST /analysis-runs (multipart)
  ├ 검증: jobUrl 필수(400 job_url_required), 파일 크기(413), MIME(415)
  ├ Redis SETNX run:lock:{userId}:{jobType}  ─┐ 둘 중 하나라도 걸리면
  ├ INSERT analysis_jobs (queued)             ─┘ 409 run_in_progress + 진행 중 runId
  ├ INSERT user_documents (extract_status='pending')
  ├ arq.enqueue('interview_prep', run_id)
  └ 202 + Location + {"runId": ...}

worker: interview_prep
  for step in [doc_extract, repo_select, repo_detail,
               jd_fetch, jd_extract, repo_analyze, match_score]:
      emit(step, 'running')     # ① UPDATE analysis_jobs.steps  ② Redis HSET  ③ PUBLISH
      ...작업...
      emit(step, 'completed')
  UPDATE status='succeeded' ; PUBLISH {"type":"completed"}
  실패 시: UPDATE status='failed', error_code=? ; PUBLISH {"type":"failed","reason":...}
```

⚠ **`emit()` 은 Postgres UPDATE → Redis → PUBLISH 순서를 지킨다.**
반대로 하면 SSE 로 `completed` 를 받은 클라이언트가 `GET /analysis-runs/{runId}` 에서 아직
`running` 을 본다.

### 락 키에 `jobType` 이 들어가는 이유

M1 `initial_sync` 는 연동 직후 백그라운드로 돈다. 사용자가 바로 공고를 입력하면 M2 와 겹치는데,
사용자 단일 락으로 두면 **정상 흐름이 `run_in_progress` 로 막힌다.**
DB 부분 유니크도 `(user_id, job_type) WHERE status IN ('queued','running')` 이다.

### 일부 실패는 job 실패가 아니다

후보 10개 중 2개가 실패해도 job 은 `succeeded` 이고 `repo_analyses` 개별 row 만 `failed` 다.
[error-reasons.md](error-reasons.md) 의 3계층 표를 따른다. `analysis_jobs.status='partial'` 을
FE 에 무엇으로 내려보낼지는 미결이다(같은 문서 미결 절).

## 3. SSE

`sse-starlette` + `realtime/bus.py`. 접속 시 순서:

1. `run:{runId}:steps` (없으면 Postgres) 를 읽어 **현재 step 상태를 먼저 흘려보낸다**
2. 그 다음 `run:{runId}:events` 구독
3. 이미 종료된 run 이면 `completed` / `failed` 하나 보내고 스트림을 닫는다

`estimatedSeconds` 는 `analysis_jobs.estimated_seconds`. 초기값은 상수(20), 이후 완료 run 의
소요시간 중앙값으로 갱신한다.

⚠ SSE 는 프록시(Vercel/Nginx)에서 버퍼링되면 죽는다. `X-Accel-Buffering: no` +
`Cache-Control: no-store` 를 응답 헤더에 넣고, 15초 주기 keep-alive 코멘트(`: ping`)를 보낸다.

---

## 4. WebSocket 면접

`GET (Upgrade) /ws/interviews/{sessionId}` — `features/interview/ws.py`

★ **스프린트1 은 양방향 텍스트다.** 오디오 프레임 · TTS · `transcript` · `stt_failed` ·
`tts_failed` 는 스프린트2 에서 붙인다 (`interview_sessions.answer_mode` CHECK = `'text'`).
클라→서버 답변 메시지 형태는 FE 와 합의가 남아 있다 — [api-spec.md](api-spec.md) ③ 참조.

### 4.1 핸드셰이크

```
1) 쿠키 → auth:sess 조회           실패 → 401 (핸드셰이크 거부, WS accept 하지 않음)
2) rt:{sessionId} 조회              없음 → 409
3) userId 일치 확인                 불일치 → 409
4) interview_sessions.status 확인   completed/abandoned → 409
5) SETNX ws:lock:{sessionId}        실패 → 409 already_connected
6) accept
```

⚠ **401/409 는 `accept()` 전에** 내야 한다. accept 후 close code 로 보내면 브라우저 쪽 구분이 어렵다.

### 4.2 메시지 ↔ DB 쓰기

| WS 메시지 | 방향 | DB / Redis |
|---|---|---|
| `prepareStep` ×4 | S→C | `interview_sessions.status='preparing'`, `context_state` 초기화 |
| `prepareCompleted` | S→C | `status='in_progress'`, `events(session_started)` |
| `question` | S→C | `INSERT interview_turns(status='asked', depth, parent_turn_no, topic_code, jd_requirement_ids, claim_ids)` + **`INSERT turn_evidences(usage='question_basis')`** + `events(turn_asked)` |
| 답변 (C→S, 텍스트 1회) | C→S | `UPDATE interview_turns SET answer_text, answered_at, answer_duration_sec, status='answered'` + `events(turn_answered)` |
| `thinking` | S→C | `UPDATE interview_turns SET analysis` (AnswerAnalysis) → `SET decision` (DirectorDecision) + `context_state` 갱신 |
| `evidenceCheck` | S→C | **`INSERT evidences(retrieved_for_turn=n, git_ref, snippet, tool_name)`** |
| (불일치 발견) | — | `INSERT evidence_conflicts(verdict='unresolved')` — **2차** |
| `interviewEnd` | S→C | `status='completed'`, `events(session_completed)`, `arq.enqueue('report_generate')` |
| 비정상 종료 | — | `status='abandoned'`, `abandoned_at_turn=turn_count`, `events(session_abandoned)` |

★ `evidenceCheck` 가 화면에 뜬 순간 `evidences` 에 행이 있어야 한다. 화면에는 떴는데 행이 없으면
그건 연출이고, 서비스가 주장하는 "근거 기반" 이 데이터로 증명되지 않는다.

★ **`turn_evidences` INSERT 누락이 가장 조용한 버그다.** 화면은 정상으로 보이고 Eval 만 깨진다.
`turn_service.py` 에서 **질문 INSERT 와 같은 트랜잭션**으로 묶어 물리적으로 빠질 수 없게 한다.

★ `turn_evidences` 필수 여부는 **페르소나별로 다르다.**

| persona | 근거 없음이 | 정상 조건 |
|---|---|---|
| `tech_lead` | **결함** | `turn_evidences` 가 있어야 한다 |
| `domain_lead` | 정상 | `jd_requirement_ids` 가 있으면 OK (JD·업종을 근거로 묻는 페르소나) |
| `hr_manager` | 정상 | `claim_ids` 가 있으면 OK (자소서 주장을 근거로 묻는 페르소나) |

### 4.3 이탈 처리

WS `disconnect` 만으로 `abandoned` 를 확정하지 않는다 (새로고침·터널 끊김과 구분 불가).
`ws:lock` 이 하트비트 없이 만료되고 재연결이 없으면 그때 `abandoned` 로 넘긴다
→ 주기 작업(`arq` cron) 1개가 필요하다.

**North Star(완주율)가 이 판정 하나에 걸려 있다.**

세션 재개는 미지원이다 (`status` 에 `paused` 없음). 답변 초안 저장도 없다 — 제출 1회.

### 4.4 두 개의 식별자 — `interviewId` ≠ `sessionId`

`POST /interviews` 가 둘을 같이 돌려주고 WS 는 `sessionId` 로 붙는다. DB 에는
`interview_sessions.id` 하나뿐이다.

| FE 필드 | 정체 | 저장소 |
|---|---|---|
| `interviewId` | `interview_sessions.id` (UUID) — 영구 식별자. 리포트·마이페이지가 참조 | Postgres |
| `sessionId` | **실시간 세션 키** — WS 연결·단일접속 락·prepare 진행 상태용 단기 토큰 | Redis `rt:{sessionId}` (TTL 2h) |

이유 두 가지. ① WS 핸드셰이크 실패 조건에 `409 already_connected` 가 있다 → 연결 단위의 짧은
수명 키가 필요하다. ② `GET /interviews/{id}` 가 `sessionId` 를 응답에 포함한다 → 새로고침 후
재연결 시 다시 받아야 하는 값이라는 뜻이다.

`rt:{sessionId}` 값에 `interviewId`, `userId` 를 담는다. Redis 가 날아가면 WS 만 끊기고 면접
기록(Postgres)은 남는다 — 그때 `GET /interviews/{id}` 가 새 `sessionId` 를 발급한다.

> ⚠ 세션 재개 미지원이 확정되면서 식별자를 2개로 나눌 근거가 약해졌다. WS 를 `interviewId` 로
> 붙이면 `rt:{sessionId}` 키가 사라진다 — FE 확정이 필요한 미결 항목이다.

### 4.5 세션 상태 — DB 4개, API 3개

| `interview_sessions.status` (DB) | FE `InterviewStatus` |
|---|---|
| `preparing` | ← **`in_progress` 로 매핑** (`currentTurn: 0`, `turns: []`) |
| `in_progress` | `in_progress` |
| `completed` | `completed` |
| `abandoned` | `abandoned` |

api-spec 이 "준비 단계면 `currentTurn: 0`, `turns: []`" 라고만 쓰고 상태값을 안 줬으므로 위처럼
접는다. DB 컬럼은 `preparing` 을 그대로 유지한다 — **준비 단계 이탈률을 봐야 한다.**
