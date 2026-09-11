# interview

상태: 초안 — frontend/md/features/interview.md에서 이관, Sprint 1 범위로 재작성.

루트 CLAUDE.md 고정 사항: **Sprint 1은 텍스트 면접이다. 음성·STT·TTS는 Sprint 2.** `spec/backend/features/interview.md`, `frontend/docs/api-spec.md`(`answerMode: "text"`, 2차에 voice 추가) 모두 동일하게 확정. 이 문서는 Sprint 1(텍스트) 기준으로 작성하고, Sprint 2(음성) 변경분은 맨 아래 별도 절에 둔다 — 지금 구현 대상 아니다.

## 목표 + 화면 구성 (Sprint 1)

WebSocket으로 AI 면접관과 텍스트 면접을 진행한다. 준비 단계와 진행 단계가 같은 WS 연결을 공유한다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 면접 준비 | 5a2-v2 | 4단계 준비 체크리스트 |
| 면접 준비 실패 | — | 준비 체크리스트(실패 단계 ✕) + 실패 배너 + `다시 시도` / `레포 다시 선택하기` |
| 면접 진행 | 5b-v2 | 면접관 표시(persona) + 질문 텍스트 + 답변 입력창(최대 2000자) + 남은 시간·턴 |

마이크·스피커 점검 섹션은 Sprint 2(음성) 항목이다 — Sprint 1 화면에는 없다.

### 5a2-v2 준비 체크리스트 4단계

`analyze_repo` → `build_persona` → `compose_question` → `set_criteria`

각 단계 `status`: `pending` | `running` | `completed` | `failed`

### 면접 준비 실패

준비 화면과 **같은 카드·같은 체크리스트를 유지**하고 실패한 단계만 빨간 ✕로 바꾼다. 이후 단계는 `pending` 그대로 남긴다.

| 영역 | 소스 |
| --- | --- |
| 체크리스트 | `prepareStep` — `completed` / `failed` / `pending` |
| 실패 배너 | `error` — 제목·본문은 `reason`별 문구, 하단에 `code` · `occurredAt` |
| 1차 액션 | `다시 시도` → `prepareRetry` 전송 |
| 2차 액션 | `레포 다시 선택하기` → 5a-v2 |
| 하단 안내 | 고객센터 링크 + "선택한 레포와 공고는 저장되어 있어요" |

`recoverable: true`면 `다시 시도` 노출, `false`면 `레포 다시 선택하기`만 노출.

### 5b-v2 진행

| 흐름 | 메시지 |
| --- | --- |
| 질문 수신 | `question` |
| 답변 전송 | `answer` (JSON, 텍스트 1회) |
| 수신 확인 | `answerReceived` |
| 생성 대기 | `thinking` · `evidenceCheck` |
| 종료 | `interviewEnd` |

`answer`는 제출 버튼 클릭 시 1회 전송한다. 초안 저장은 없다.

## 화면 이동 순서

```
5a-v2 [확정] → POST /interviews → 201 { sessionId, interviewId }
                                     ↓
5a2-v2  면접 준비
  ├─ GET /interviews/{id} → status === 'preparing' 확인
  ├─ WS 연결 → prepareStep 수신
  ├─ prepareCompleted → 5b-v2
  └─ error            → 면접 준비 실패

면접 준비 실패
  ├─ [다시 시도]            → prepareRetry → 5a2-v2 (실패 단계부터 재실행)
  └─ [레포 다시 선택하기]    → 5a-v2 (새 세션 생성, 기존 세션은 abandoned)

5b-v2  면접 진행 (WS 유지)
  ├─ interviewEnd → 5c-v2 리포트
  ├─ [이탈 확인 모달에서 확인] → 명시적 이탈, status='abandoned'
  └─ onclose      → GET /interviews/{id} → 토큰 갱신 + turns 복구 → WS 재연결 (실패해도 계속 재시도)
```

### 새로고침·재진입 복구

`GET /interviews/{id}`의 `status`로 도달 화면을 결정한다.

| `status` | 화면 |
| --- | --- |
| `preparing` | 5a2-v2 (`turns: []`, `currentTurn: 0`) |
| `in_progress` | 5b-v2 (`turns`로 복구) |
| `completed` | 5c-v2 |
| `preparing_failed` | 면접 준비 실패 — `lastError`로 배너 렌더 (WS 재연결 없이 REST 스냅샷만으로 그린다) |
| `abandoned` | "중단된 면접이에요" 안내 후 `/home` |

BE는 준비 실패를 `abandoned`와 분리하기 위해 `preparing_failed`를 둔다(`ForFE.md` #6, `spec/backend/features/interview.md`). 이 값을 놓치면 새로고침 시 면접 준비 실패 화면과 완전 이탈(`abandoned`)이 화면상 구분되지 않는다.

### abandoned 판정 정책 (Sprint 1)

Sprint 1은 이탈 자동 감지 배치/주기 job이 없다(`context/DB.md`: "timeout 값을 1차에 안 쓰는 것을 권장 — 배치 작업 하나를 안 만들어도 되고"; `spec/backend/architecture.md` "Sprint 2 방향"도 이탈/복구 정책 자체를 Sprint 2 추가 항목으로 명시). 그래서 `abandoned`는 오직 **명시적 이벤트**로만 세팅된다.

- 이탈 확인 모달에서 사용자가 명시적으로 나가기를 확인했을 때
- 레포를 다시 선택해 새 세션을 만들 때(기존 세션)

**연결 끊김·재연결 실패는 그 자체로 `abandoned` 전환 트리거가 아니다.** FE는 `onclose` 시 몇 번이고 재연결을 시도한다 — 실패한다고 세션 상태를 바꾸지 않는다(바꿀 자동 판정 정책 자체가 Sprint 1에 없다). 재연결이 계속 실패하면 화면에는 "연결이 끊겼어요" 같은 연결 상태 안내만 띄우고, 세션 상태 전환은 하지 않는다.

## API 연동

| # | 엔드포인트 | 화면 | queryKey |
| --- | --- | --- | --- |
| 17 | `GET /interviews/{id}` | 5a2-v2, 5b-v2, 면접 준비 실패 | `['interview', id]` |
| 18 | `GET (Upgrade) /ws/interviews/{sessionId}` | 5a2-v2, 5b-v2 | — |

`GET /interviews/{id}` 응답에 `answerMode: "text"`가 포함된다. Sprint 1은 이 값을 항상 `text`로 취급하지만, 화면 로직은 이 값으로 분기하도록 만들어 Sprint 2에서 `voice`가 추가돼도 값을 무시하지 않게 한다.

이 엔드포인트는 인터뷰가 존재하는 한 상태와 무관하게 `200`이다 — "인터뷰 시작 조건"이 아니라 상태 조회용 단일 엔드포인트다. `status`가 5가지(`preparing`/`in_progress`/`completed`/`preparing_failed`/`abandoned`) 중 무엇인지로 화면을 나눈다.

**BE 반영 필요**: 응답에 `lastError` 필드 추가.

```json
{
  "status": "preparing_failed",
  "lastError": {
    "reason": "question_gen_timeout",
    "code": "ERR_QUESTION_GEN_TIMEOUT",
    "step": "compose_question",
    "recoverable": true,
    "occurredAt": "2026-09-07T14:22:10Z"
  }
}
```

`status !== 'preparing_failed'`면 `lastError`는 `null`이다. WS `error` 이벤트로 받는 실시간 배너와 필드 구성이 같다 — 새로고침 시 WS 재연결 없이 이 스냅샷만으로 면접 준비 실패 배너를 완성한다.

### 핸드셰이크

```
GET /api/ws/interviews/sess_xyz789 HTTP/1.1
Upgrade: websocket
Connection: Upgrade
Cookie: accessToken=<jwt>
```

쿠키는 same-origin이므로 브라우저가 자동 첨부한다. 별도 코드 없음.

**`/api` 프리픽스 직접 붙여야 함**: `fetch` 호출은 `shared/api.ts`가 자동으로 `/api`를 붙여주지만(`const BASE = '/api'`), `WebSocket`은 이 래퍼를 거치지 않는다. WS 연결 문자열에 `/api`를 빠뜨리면 CloudFront rewrite(`/api/:path*` → BE)를 안 타서 화면 경로로 오인되고 핸드셰이크가 실패한다. `spec/frontend/architecture.md`의 "`/api` 프리픽스" 참고.

| 코드 | 상황 |
| --- | --- |
| 401 | 쿠키 없음 · 만료 · 변조 |
| 409 | 이미 종료된 세션 · `already_connected` |

인증은 핸드셰이크 시 1회만 검증한다. **연결 유지 중 액세스 토큰이 만료되어도 연결을 끊지 않는다.**

재연결 시에는 핸드셰이크를 다시 하므로 만료 토큰이면 401이다. `onclose` 후 반드시 `GET /interviews/{id}`를 먼저 호출한다 — 이 요청이 401 인터셉터를 타면서 토큰이 갱신되고 동시에 복구용 `turns`를 확보한다. **순서를 바꾸면 만료 토큰으로 핸드셰이크를 시도해 401이 반복된다.**

### 클라이언트 → 서버

```json
{ "type": "prepareRetry" }
{ "type": "answer", "text": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다." }
```

| type | 필드 |
| --- | --- |
| `prepareRetry` | — |
| `answer` | `text` (string, 최대 2000자) |

`prepareRetry`는 준비 단계가 실패한 뒤 "다시 시도"를 눌렀을 때 보낸다. 서버는 실패한 `prepareStepKey`부터 다시 실행하고, 성공한 단계는 재실행하지 않는다.

`answer`는 2000자 초과 시 `answer_too_long`.

### 서버 → 클라이언트

| type | 필드 | 처리 |
| --- | --- | --- |
| `prepareStep` | `key`, `status` | 준비 체크리스트 갱신 |
| `prepareCompleted` | — | 5b-v2 전환 |
| `answerReceived` | — | 제출 중 상태 해제, 입력창 잠금 해제 |
| `thinking` | — | 생성 중 인디케이터 |
| `evidenceCheck` | `repository`, `file` | 근거 확인 배너 |
| `question` | `persona`, `text`, `turn` | 질문 표시 |
| `interviewEnd` | — | 5c-v2 이동 |
| `error` | `reason`, `recoverable`, `code`, `step`, `occurredAt` | 분기 처리 |

`answerReceived`는 서버가 답변 수신·저장을 완료했다는 신호다. `answer` 전송 후 이 메시지를 받기 전까지 제출 중 상태를 유지하고 입력창을 잠근다.

`evidenceCheck` 배너는 `evidenceCheck` 외 다른 서버 메시지를 수신하면 해제한다. 30초간 메시지가 없으면 타임아웃 해제.

준비 실패 시 메시지 순서

```
{ "type": "prepareStep", "key": "analyze_repo",     "status": "completed" }
{ "type": "prepareStep", "key": "build_persona",    "status": "completed" }
{ "type": "prepareStep", "key": "compose_question", "status": "failed" }
{ "type": "error", "reason": "question_gen_timeout", "recoverable": true,
  "code": "ERR_QUESTION_GEN_TIMEOUT", "step": "compose_question",
  "occurredAt": "2026-09-07T14:22:10Z" }
```

### error.reason 분기 (Sprint 1)

| reason | `code` | `recoverable` | 처리 |
| --- | --- | --- | --- |
| `answer_too_long` | `ERR_ANSWER_TOO_LONG` | ✅ | 같은 턴 재제출 |
| `answer_rejected` | `ERR_ANSWER_REJECTED` | ✅ | 같은 턴 재제출 (저장 실패) |
| `question_failed` | `ERR_QUESTION_FAILED` | ✅ | 자동 1회 재시도 |
| `question_gen_timeout` | `ERR_QUESTION_GEN_TIMEOUT` | ✅ | 면접 준비 실패 — `prepareRetry` |
| `persona_build_failed` | `ERR_PERSONA_BUILD_FAILED` | ✅ | 면접 준비 실패 — `prepareRetry` |
| `criteria_set_failed` | `ERR_CRITERIA_SET_FAILED` | ✅ | 면접 준비 실패 — `prepareRetry` |
| `repo_analyze_failed` | `ERR_REPO_ANALYZE_FAILED` | ✅ | 면접 준비 실패 — `prepareRetry` |
| `github_api_rate_limited` | `ERR_GITHUB_RATE_LIMITED` | ✅ | 면접 준비 실패 — 대기 후 `prepareRetry` |
| `repo_unreachable` | `ERR_REPO_UNREACHABLE` | ❌ | 레포 재선택 |
| `github_token_invalid` | `ERR_GITHUB_TOKEN_INVALID` | ❌ | GitHub 재연동 |

`stt_failed`·`tts_failed`는 Sprint 2 전용이라 Sprint 1에는 없다.

`recoverable: false`면 서버가 세션을 종료하고 연결을 닫는다.
`code`는 화면에 그대로 노출하는 표시용 식별자다. `occurredAt`과 함께 배너 하단에 표기한다.
`step`은 준비 단계 오류일 때만 값이 있고, 진행 중 오류에서는 `null`이다.

### 타이머

`remainingSeconds`는 서버 시각 기준(`planned_duration_sec - elapsed_sec`)이다. 재연결 시 클라이언트 타이머를 이 값으로 덮어쓴다.

## 상태 요구사항 (Sprint 1)

**이 기능은 서버 상태와 실시간 상태가 공존한다. 경계를 명확히 둔다.**

```
복구는 Query  — GET /interviews/{id} (스냅샷)
진행은 store  — WS로 흘러오는 턴 상태
```

### 실시간 세션 상태 (store 또는 Context + reducer — 라이브러리 미확정)

| 상태 | 용도 |
| --- | --- |
| `prepareSteps` | 준비 4단계 status |
| `wsStatus` | `connecting` / `open` / `closed` / `reconnecting` |
| `currentTurn` | 현재 턴 번호 |
| `turns` | 누적 질문·답변 (초기값은 Query 스냅샷) |
| `phase` | `preparing` / `asking` / `answering` / `submitting` / `thinking` |
| `evidenceBanner` | `{ repository, file }` 또는 `null` |
| `lastError` | `{ reason, code, step, occurredAt, recoverable }` |
| `remainingSeconds` | 서버값으로 초기화한 카운트다운 |

### 화면 로컬 상태

| 상태 | 용도 |
| --- | --- |
| `answerDraft` | 답변 입력창 텍스트 (2000자 제한) |
| `isSubmitting` | 제출 중 — `answer` 전송 후 `answerReceived` 전까지 입력창 잠금 |
| `isLeaveModalOpen` | 이탈 확인 모달 |

구현 시 리렌더 안전성 주의사항은 `frontend/docs/task-10-interview.md` 참고.

## 검증 시나리오 (Sprint 1)

- 준비 4단계 체크리스트 실시간 갱신
- 준비 실패 → 면접 준비 실패 화면 전환, 실패 단계만 ✕ 표시
- `recoverable` true/false에 따라 버튼 노출 분기
- 2000자 초과 → `answer_too_long` 처리, 같은 턴 재제출
- `error.reason` 분기 확인 (Sprint 1 9종)
- `onclose` 재연결 시 GET 먼저 호출 순서 확인 (401 반복 안 남)
- 새로고침 시 `status`별 복구 화면 확인 (`preparing_failed` 포함)
- `preparing_failed` 새로고침 시 WS 없이 `lastError`만으로 면접 준비 실패 배너 렌더 확인
- `remainingSeconds` 서버값으로 동기화

---

## Sprint 2 (음성) — 지금 구현 대상 아님

`answerMode: "voice"`가 추가되면 달라지는 부분만 기록한다. 상세 설계는 Sprint 2 착수 시 다시 브레인스토밍한다.

| 항목 | Sprint 1 | Sprint 2 |
| --- | --- | --- |
| 화면 구성 | 텍스트 입력창 | 마이크·스피커 점검 섹션, 녹음 컨트롤, 전사 표시 |
| 답변 전송 | `answer` 1회 (JSON) | `answerStart` → 오디오 바이너리 → `answerEnd` |
| 서버 메시지 | — | `transcript`, `questionEnd` |
| 신규 error reason | — | `stt_failed`, `tts_failed` |
| 오디오 포맷 | — | `audio/webm; codecs=opus`, 48000Hz, mono, 최대 180초 |

`answerMode`로 화면 로직을 분기하게 만들어 두면 Sprint 2 전환 시 이 값을 무시하지 않아도 된다.
