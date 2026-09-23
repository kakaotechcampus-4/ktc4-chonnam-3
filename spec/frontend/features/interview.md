# interview

상태: 초안 — frontend/md/features/interview.md에서 이관, Sprint 1 범위로 재작성.

[0010 결정](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 **Sprint 1은 텍스트 면접이며 음성·STT·TTS는 Sprint 2**다. 이 문서는 Sprint 1 기준이며 Sprint 2 참고안은 맨 아래 구분한다. 로컬 면접 준비·진행 화면은 골격이므로 아래 동작은 [task-10](../../../frontend/docs/task-10-interview.md)의 구현·검증 대상으로 읽는다.

## 목표 + 화면 구성 (Sprint 1)

WebSocket으로 AI 면접관과 텍스트 면접을 진행한다. 준비 단계와 진행 단계가 같은 WS 연결을 공유한다.

[공통 0004](../../shared/decisions/0004-flexible-persona-allocation-restoration.md)에 따라 정상 완료는 9턴이며 첫 질문은 HR이다. 기술 질문은 목표 6턴·최소 5턴, 도메인·HR 질문은 첫 HR을 포함해 합산 최소 3턴이다. 도메인·HR의 개별 배분과 첫 질문 이후의 순서는 고정하지 않으며 HR을 다시 선택할 수 있다. 역할 배분 로직의 구현 완료를 뜻하지 않는다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 면접 준비 | 5a2-v2 | 4단계 준비 체크리스트 |
| 면접 준비 실패 | — | 준비 체크리스트(실패 단계 ✕) + 실패 배너 + `다시 시도` / `레포 다시 선택하기` |
| 면접 진행 | 5b-v2 | 면접관 표시(persona) + 질문 텍스트 + 답변 입력창(최대 2000자) + 남은 시간·턴 |

마이크·스피커 점검 섹션은 Sprint 2(음성) 항목이다 — Sprint 1 화면에는 없다.

### 5a2-v2 준비 체크리스트 4단계

`analyze_repo` → `build_persona` → `set_criteria` → `compose_question`

각 단계 `status`: `pending` | `running` | `completed` | `failed`

### 면접 준비 실패

준비 화면과 **같은 카드·같은 체크리스트를 유지**하고 실패한 단계만 빨간 ✕로 바꾼다. 이후 단계는 `pending` 그대로 남긴다.

| 영역 | 소스 |
| --- | --- |
| 체크리스트 | `prepareStep` — `completed` / `failed` / `pending` |
| 실패 배너 | `error` — 제목·본문은 `reason`별 문구, 하단에 `code` · `occurredAt` |
| 1차 액션 | `다시 시도` → `POST /interviews/{id}/prepare/retry` |
| 2차 액션 | `레포 다시 선택하기` → 5a-v2 |
| 하단 안내 | 고객센터 안내 문구 + "선택한 레포와 공고는 저장되어 있어요" — 고객센터 페이지 추가 전까지는 링크 없이 텍스트 (mypage.md:33과 동일). 페이지가 생기면 `Link`로 연결 |

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
  ├─ [다시 시도]            → POST /interviews/{id}/prepare/retry → 5a2-v2 (실패 단계부터 재실행)
  └─ [레포 다시 선택하기]    → 5a-v2 (새 세션 생성, 기존 세션은 abandoned)

5b-v2  면접 진행 (WS 유지)
  ├─ interviewEnd → 5c-v2 리포트
  ├─ [이탈 확인 모달에서 확인] → 명시적 이탈, status='abandoned'
  └─ onclose      → GET /interviews/{id} → 세션 확인 + turns 복구 → WS 재연결 (인증 만료·유실은 /login)
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

공통 계약과 [BE 면접 명세](../../backend/features/interview.md)는 준비 실패를 `abandoned`와 분리하기 위해 `preparing_failed`를 둔다. 이 값을 놓치면 새로고침 시 면접 준비 실패 화면과 완전 이탈이 구분되지 않는다.

### abandoned 판정 정책 (Sprint 1)

[0010 결정](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 Sprint 1은 heartbeat·timeout 기반 자동 이탈 판정을 하지 않는다. `abandoned`는 다음 **명시적 이벤트**로만 설정한다.

- 이탈 확인 모달에서 사용자가 명시적으로 나가기를 확인했을 때
- 레포를 다시 선택해 새 세션을 만들 때(기존 세션)

**연결 끊김·재연결 실패는 그 자체로 `abandoned` 전환 트리거가 아니다.** FE는 인증이 유효한 동안 `onclose` 후 재연결을 계속 시도한다. `401 unauthenticated`이면 refresh 없이 캐시를 비우고 `/login`으로 이동하며, 이 동작만으로 면접을 `abandoned`로 바꾸지 않는다. 그 밖의 재연결 실패가 계속되면 "연결이 끊겼어요" 같은 안내만 띄우고 면접 상태는 전환하지 않는다.

명시적으로 나간 뒤에도 이미 저장한 답변 원문은 보존한다. 마지막 턴이 미답변일 때만 `answer: null`이며, 답변 저장 후 분석·질문 생성 중 나간 경우 저장된 답변을 지우지 않는다.

## API 연동

| # | 엔드포인트 | 화면 | queryKey |
| --- | --- | --- | --- |
| 17 | `GET /interviews/{id}` | 5a2-v2, 5b-v2, 면접 준비 실패 | `['interview', id]` |
| 18 | `GET (Upgrade) /ws/interviews/{sessionId}` | 5a2-v2, 5b-v2 | — |
| — | `POST /interviews/{id}/prepare/retry` | 면접 준비 실패 | — |

`GET /interviews/{id}` 응답에 `answerMode: "text"`가 포함된다. Sprint 1은 이 값을 항상 `text`로 취급하지만, 화면 로직은 이 값으로 분기하도록 만들어 Sprint 2에서 `voice`가 추가돼도 값을 무시하지 않게 한다.

이 엔드포인트는 인터뷰가 존재하는 한 상태와 무관하게 `200`이다 — "인터뷰 시작 조건"이 아니라 상태 조회용 단일 엔드포인트다. `status`가 5가지(`preparing`/`in_progress`/`completed`/`preparing_failed`/`abandoned`) 중 무엇인지로 화면을 나눈다.

`lastError`는 이미 공통 OpenAPI 응답에 포함된 필드다. 실제 BE 응답과 화면 복구 연결은 구현·검증할 대상이며 새 API 필드 추가 결정이 아니다.

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
Cookie: devon_session=<sid>
```

쿠키는 same-origin이므로 브라우저가 자동 첨부한다. [0003 결정](../../shared/decisions/0003-sprint1-session-auth.md)에 따라 REST·SSE·WS는 같은 Redis 로그인 세션을 확인한다. 로그인 쿠키의 `sid`와 WS 경로의 면접 `sessionId`는 별개이며 기존 공개 ID를 바꾸지 않는다.

**`/api` 프리픽스 직접 붙여야 함**: `fetch` 호출은 `shared/api.ts`가 자동으로 `/api`를 붙여주지만(`const BASE = '/api'`), `WebSocket`은 이 래퍼를 거치지 않는다. WS 연결 문자열에 `/api`를 빠뜨리면 Caddy의 `/api/*` reverse proxy를 안 타서 화면 경로로 오인되고 핸드셰이크가 실패한다. `spec/frontend/architecture.md`의 "`/api` 프리픽스" 참고.

| 코드 | 상황 |
| --- | --- |
| 401 | `unauthenticated` — 로그인 쿠키 없음 · 세션 만료/유실/무효 |
| 409 | 이미 종료된 세션 · `already_connected` |

인증은 핸드셰이크 시 1회만 검증한다. **연결 유지 중 로그인 세션이 만료됐다는 이유로 기존 연결을 끊는 정책은 추가하지 않는다.**

재연결 시에는 핸드셰이크를 다시 검증한다. `onclose` 후 `GET /interviews/{id}`를 먼저 호출해 로그인 세션이 유효한지 확인하고 복구용 `turns`를 확보한 뒤 WS를 다시 연결한다. 세션이 만료·유실됐으면 `401 unauthenticated`를 공통 처리해 캐시를 비우고 `/login`으로 이동한다. JWT refresh 호출이나 만료 인증으로 계속 재연결하는 동작은 없다.

### 클라이언트 → 서버

```json
{ "type": "answer", "turn": 3, "text": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다." }
```

| type | 필드 |
| --- | --- |
| `answer` | `turn` (number), `text` (string, 최대 2000자) |

준비 단계가 실패한 뒤 "다시 시도"를 누르면 WS 메시지가 아니라 `POST /interviews/{id}/prepare/retry`를 호출한다. 서버는 실패한 `prepareStepKey`부터 다시 실행하고, 성공한 단계는 재실행하지 않는다.

`answer`는 현재 답변 가능한 turn과 일치해야 한다. 2000자 초과 시 `answer_too_long`.

### 서버 → 클라이언트

| type | 필드 | 처리 |
| --- | --- | --- |
| `prepareStep` | `key`, `status` | 준비 체크리스트 갱신 |
| `prepareCompleted` | — | 5b-v2 전환 |
| `answerReceived` | — | 제출 중 상태 해제, 입력창은 다음 `question`까지 잠금 유지 |
| `thinking` | — | 생성 중 인디케이터 |
| `evidenceCheck` | `repository`, `file` | 근거 확인 배너 |
| `question` | `persona`, `text`, `turn` | 질문 표시 |
| `interviewEnd` | — | 5c-v2 이동 |
| `error` | `reason`, `recoverable`, `code`, `step`, `occurredAt` | 분기 처리 |

`answerReceived`는 서버가 답변 수신·저장을 완료했다는 신호다. `answer` 전송 후 이 메시지를 받기 전까지 제출 중 상태를 유지하고 입력창을 잠근다. 수신 뒤에는 제출 중 상태만 해제하고, 다음 `question`이 도착할 때까지 새 답변 입력은 열지 않는다.

Sprint 1의 `question` 수신은 질문 전달 완료를 뜻하며 `questionEnd`를 별도로 기다리지 않는다.

`evidenceCheck` 배너는 `evidenceCheck` 외 다른 서버 메시지를 수신하면 해제한다. 30초간 메시지가 없으면 타임아웃 해제.

준비 실패 시 메시지 순서

```
{ "type": "prepareStep", "key": "analyze_repo",     "status": "completed" }
{ "type": "prepareStep", "key": "build_persona",    "status": "completed" }
{ "type": "prepareStep", "key": "set_criteria",     "status": "completed" }
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
| `question_failed` | `ERR_QUESTION_FAILED` | ✅ | 허용된 시도 후 실패 안내·기록 보존·명시적 나가기 (아래 재시도 책임 참고) |
| `question_gen_timeout` | `ERR_QUESTION_GEN_TIMEOUT` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `persona_build_failed` | `ERR_PERSONA_BUILD_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `criteria_set_failed` | `ERR_CRITERIA_SET_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `repo_analyze_failed` | `ERR_REPO_ANALYZE_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `github_api_rate_limited` | `ERR_GITHUB_RATE_LIMITED` | ✅ | 면접 준비 실패 — 대기 후 `POST /interviews/{id}/prepare/retry` |
| `repo_unreachable` | `ERR_REPO_UNREACHABLE` | ❌ | 레포 재선택 |
| `github_token_invalid` | `ERR_GITHUB_TOKEN_INVALID` | ❌ | GitHub 재연동 |

`stt_failed`·`tts_failed`는 Sprint 2 전용이라 Sprint 1에는 없다.

`error`는 `reason`과 `recoverable`을 함께 보고 위 원인별 처리로 분기한다. [0010 결정](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 LLM의 timeout/provider 오류·parse/schema 실패만 공통 호출 계층에서 자동 1회 재시도한다(최초 호출 포함 최대 2회). semantic 실패는 재호출하지 않는다. `question_failed`의 기존 `recoverable: true`만으로 FE가 추가 재시도하거나 재연결로 LLM을 다시 호출하지 않는다.

허용된 시도 후에도 질문 생성에 실패하면 [기존 면접 실패 정책](../../ai/features/interviewer.md#공개-메시지와-보류-항목)에 따라 오류 안내·기록 보존·명시적 나가기와 새 면접 흐름을 유지한다. 진행 중 면접의 새 수동 이어가기는 추가하지 않는다.

`recoverable: false`면 서버가 WS 연결을 닫는다. 오류 안내나 연결 종료만으로 DB 상태를 `completed` 또는 `abandoned`로 바꾸지 않는다. 정상 완료는 9번째 답변 처리 완료, `abandoned`는 명시적 나가기 확인·레포 재선택에 따른다. 오류 전달·종료 요청·실패 기록 복원의 실제 연결은 구현·검증 대상이다.

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
- `reason`·`recoverable`에 맞는 안내와 액션 표시; `question_failed`에서 FE·재연결의 추가 LLM 재시도 없음
- 2000자 초과 → `answer_too_long` 처리, 같은 턴 재제출
- `error.reason` 분기 확인 (Sprint 1 9종)
- `onclose` 재연결 시 GET으로 세션·turns 먼저 확인; 401이면 refresh 없이 로그인 이동
- 새로고침 시 `status`별 복구 화면 확인 (`preparing_failed` 포함)
- `preparing_failed` 새로고침 시 WS 없이 `lastError`만으로 면접 준비 실패 배너 렌더 확인
- 오류·연결 종료만으로 DB 종료 상태를 바꾸지 않고, 명시적 이탈 뒤에도 저장 답변을 보존함
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
