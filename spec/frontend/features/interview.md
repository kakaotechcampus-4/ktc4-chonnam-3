# interview

상태: 초안 — frontend/md/features/interview.md에서 이관, Sprint 1 범위로 재작성.

[0010 결정](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 **Sprint 1은 텍스트 면접이며 음성·STT·TTS는 Sprint 2**다. 이 문서는 Sprint 1 기준이며 Sprint 2 참고안은 맨 아래 구분한다. 로컬 면접 준비·진행 화면은 골격이므로 아래 동작은 [task-10](../../../frontend/docs/task-10-interview.md)의 구현·검증 대상으로 읽는다.

## 목표 + 화면 구성 (Sprint 1)

WebSocket으로 AI 면접관과 텍스트 면접을 진행한다. 준비 단계와 진행 단계가 같은 WS 연결을 공유한다.

[공통 0008](../../shared/decisions/0008-fixed-persona-allocation.md)에 따라 정상 완료 9턴은 기술 6회·도메인 2회·HR 1회이며 첫 질문이 유일한 HR 질문이다. 이후 기술·도메인 순서는 고정하지 않으며 FE는 서버가 전달한 Persona를 표시한다. 9번째 답변 처리 후 종료하고, 이탈·실패로 중단된 면접에는 정상 배분을 강제하지 않는다. 제한 시간이 다 돼 9턴을 못 채우고 끝난 면접도 `completed`이며 배분을 강제하지 않는다([공통 0013](../../shared/decisions/0013-interview-time-limit-and-early-end-report.md)). 이번 반영은 문서에 한정하며 실제 제어·mock 정합성·검증 상태는 [AI 구현 기록](../../ai/implementation.md)을 따른다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 면접 준비 | 5a2-v2 | 4단계 준비 체크리스트 + 마이크·스피커 점검 |
| 면접 준비 실패 | — | 준비 체크리스트(실패 단계 ✕) + 실패 배너 + `다시 시도` / `레포 다시 선택하기` |
| 면접 진행 | 5b-v2 | 면접관 표시(persona) + 질문 텍스트 + 답변 입력창(최대 2000자) + 남은 시간·턴 |

Sprint 2부터 면접은 음성만 남는다. 그 선행 작업으로 면접 준비 화면(5a2-v2)에는 `answerMode`와 무관하게 마이크·스피커 점검 섹션을 항상 띄운다. 면접 진행 화면이 음성으로 바뀌기 전까지는 점검만 하고 답변은 여전히 텍스트다.

- 장치 선택: 화면 진입 시 마이크 권한을 확인하고 바로 닫는다. 결과는 배지로 표시한다 — `확인 중` / `✓ 정상 감지됨` / `권한 거부됨` / `마이크 없음` / `마이크 사용 중`(다른 앱이 점유) / `확인 실패`(비보안 주소 등). 문제가 있으면 해결 안내를 한 줄 붙이고, `확인 실패`를 뺀 경우에는 `다시 확인` 버튼으로 다시 요청한다. 사이트 설정에서 권한이 바뀌면(권한 상태 API 지원 브라우저) 새로고침 없이 다시 확인한다. 권한이 있으면 마이크·스피커 목록을 드롭다운으로 보여주고, 장치를 꽂거나 뽑으면 목록을 다시 읽는다. 스피커 선택은 지원 브라우저(Chrome·Edge)에서만 보이고, 그 외에는 기본 스피커를 쓴다.
- 마이크 테스트: 녹음 후 재생 방식이다. `마이크 테스트`를 누르면 선택한 마이크로 최대 5초 녹음하며 입력 크기를 레벨 미터로 보여준다. `녹음 끝내기`를 누르거나 5초가 지나면 마이크를 닫고 녹음을 선택한 스피커로 재생한다. 실시간으로 스피커에 내보내지 않는다 — 하울링이 나고 브라우저 에코 제거가 소리를 끊기게 만든다. 마이크 변경·화면 이탈 시 녹음·재생을 멈추고 마이크를 닫는다.
- 스피커 테스트: `테스트 재생`으로 선택한 스피커에 1초 비프음을 재생한다.
- 마이크가 `✓ 정상 감지됨`이 아니면 `면접 시작하기`를 막고 "마이크를 확인해야 면접을 시작할 수 있어요"를 표시한다. 음성 면접은 마이크 없이 답변할 수 없으므로 타이머가 돌기 전에 해결하게 한다. `다시 확인`이나 권한 변경으로 정상이 되면 바로 풀린다. 스피커는 감지할 수 없어 막지 않는다.

### 5a2-v2 준비 체크리스트 4단계

`analyze_repo` → `build_persona` → `set_criteria` → `compose_question`

각 단계 `status`: `pending` | `running` | `completed` | `failed`

### 면접 준비 실패

준비 화면과 **같은 카드·같은 체크리스트를 유지**하고 실패한 단계만 빨간 ✕로 바꾼다. 이후 단계는 `pending` 그대로 남긴다.

| 영역 | 소스 |
| --- | --- |
| 체크리스트 | `prepareStep` — `completed` / `failed` / `pending` |
| 실패 배너 | `error` — 제목·본문은 `reason`별 문구. `code` · `occurredAt`은 노출하지 않는다 |
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
  └─ [레포 다시 선택하기]    → 5a-v2 (기존 면접 id 전달) → [면접 시작] → 기존 면접 abandon → 새 면접 생성

5b-v2  면접 진행 (WS 유지)
  ├─ interviewEnd → 5c-v2 리포트
  ├─ [이탈 확인 모달에서 확인] → POST /interviews/{id}/abandon → /home
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

### abandoned 전환 방법

[공통 0009](../../shared/decisions/0009-interview-abandon-transition.md)에 따라 위 두 이벤트를 `POST /interviews/{id}/abandon`으로 서버에 알린다.

- 나가기: 이탈 모달 확인 → `POST /interviews/{id}/abandon` → `/home`. 요청이 실패해도 홈으로 이동한다. `409 already_completed`면 `GET /interviews/{id}`로 다시 확인해 `completed`일 때만 리포트로 이동한다. 이 reason은 `preparing`(다른 탭의 [다시 시도])에도 온다.
- 레포 재선택(준비 실패·진행 중 `repo_unreachable` 모두): [레포 다시 선택하기]는 기존 면접 id를 넘기며 레포 선택 화면으로 이동만 한다. 레포 선택 화면의 [면접 시작]에서 기존 면접 abandon → `POST /interviews` 순서로 보낸다. abandon만 성공하고 생성이 실패하면 레포 선택 화면에 머문다. 생성이 `410 run_expired`면 다시 눌러도 같으므로 공고 입력부터 다시 시작하도록 안내한다. abandon이 `409 already_completed`면 나가기와 같이 다시 확인하고, `completed`가 아니면 조회한 `status`의 화면으로 이동한다.
- 면접 생성 후 준비 화면 이동은 `replace`로 해, 뒤로 가기로 같은 run의 레포 선택 화면에 돌아오지 않게 한다.
- abandon 시 서버가 열린 WS를 닫는다. FE는 기존 `onclose` 처리대로 `GET /interviews/{id}`로 확인하고 `abandoned`면 재연결하지 않는다.

## API 연동

| # | 엔드포인트 | 화면 | queryKey |
| --- | --- | --- | --- |
| 17 | `GET /interviews/{id}` | 5a2-v2, 5b-v2, 면접 준비 실패 | `['interview', id]` |
| 18 | `GET (Upgrade) /ws/interviews/{sessionId}` | 5a2-v2, 5b-v2 | — |
| — | `POST /interviews/{id}/prepare/retry` | 면접 준비 실패 | — |
| — | `POST /interviews/{id}/abandon` | 5b-v2 이탈 모달, 레포 재선택 | — |

`GET /interviews/{id}` 응답에 `answerMode: "text"`가 포함된다. Sprint 1은 이 값을 항상 `text`로 취급한다. 준비 화면의 장치 점검은 이 값으로 분기하지 않는다. Sprint 2에 텍스트 면접을 없애면서 이 필드를 어떻게 정리할지는 공통 계약 결정으로 따로 남긴다.

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
| `question_failed` | `ERR_QUESTION_FAILED` | ❌ 진행 중 분석·질문 생성 실패 / ✅ 연결 교체·서버 오류 | ❌: GET이 허용하면 저장된 답변으로 #27 이어가기. 복구가 불가능하면 [같은 레포로 다시 시작](abandon → `POST /interviews/{id}/retry` → 새 면접 준비) · [나가기](abandon → 홈). retry 실패 안내는 재도전과 같다. ✅: 재연결 ([공통 0010](../../shared/decisions/0010-in-progress-question-failed-unrecoverable.md)) |
| `question_gen_timeout` | `ERR_QUESTION_GEN_TIMEOUT` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `persona_build_failed` | `ERR_PERSONA_BUILD_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `criteria_set_failed` | `ERR_CRITERIA_SET_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `repo_analyze_failed` | `ERR_REPO_ANALYZE_FAILED` | ✅ | 면접 준비 실패 — `POST /interviews/{id}/prepare/retry` |
| `github_api_rate_limited` | `ERR_GITHUB_RATE_LIMITED` | ✅ | 면접 준비 실패 — 대기 후 `POST /interviews/{id}/prepare/retry` |
| `repo_unreachable` | `ERR_REPO_UNREACHABLE` | ❌ | 레포 재선택 |
| `github_token_invalid` | `ERR_GITHUB_TOKEN_INVALID` | ❌ | GitHub 재연동 |

`stt_failed`·`tts_failed`는 Sprint 2 전용이라 Sprint 1에는 없다.

`error`는 `reason`과 `recoverable`을 함께 보고 위 원인별 처리로 분기한다. [0010 결정](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 LLM의 timeout/provider 오류·parse/schema 실패만 공통 호출 계층에서 자동 1회 재시도한다(최초 호출 포함 최대 2회). semantic 실패는 재호출하지 않는다. 진행 중 분석·질문 생성이 실패하면 `question_failed`는 `recoverable: false`로 온다([공통 0010](../../shared/decisions/0010-in-progress-question-failed-unrecoverable.md)). 연결 교체·서버 오류의 `recoverable: true`도 FE가 추가 재시도하거나 재연결로 LLM을 다시 호출하는 근거가 아니다.

허용된 시도 후에도 질문 생성에 실패하면 [기존 면접 실패 정책](../../ai/features/interviewer.md#공개-메시지와-미구현-항목)에 따라 오류 안내·기록 보존·명시적 나가기와 새 면접 흐름을 유지한다. [공통 0012](../../shared/decisions/0012-bounded-question-recovery.md)에 따라 저장 T3 이후 다음 질문 실패에만 서버가 허용한 명시 수동 이어가기 1라운드를 제공한다. GET의 questionRetryState로 요청 ID·진행 상태를 복원하며 새 UUID나 답변 재전송으로 우회하지 않는다. 실패한 면접은 `in_progress`로 남으므로 FE는 abandon을 먼저 보낸 뒤 같은 레포로 재도전하거나 홈으로 나가게 한다(abandon 없이 홈으로 보내면 같은 run의 새 면접이 `409 session_limit_exceeded`가 된다).

`recoverable: false`면 서버가 WS 연결을 닫는다. 오류 안내나 연결 종료만으로 DB 상태를 `completed` 또는 `abandoned`로 바꾸지 않는다. 정상 완료는 9번째 답변 처리 완료 또는 제한 시간 만료([공통 0013](../../shared/decisions/0013-interview-time-limit-and-early-end-report.md)), `abandoned`는 명시적 나가기 확인·레포 재선택에 따른다. 오류 전달·종료 요청·실패 기록 복원의 실제 연결은 구현·검증 대상이다.

`code`·`occurredAt`은 화면에 노출하지 않는다. 사용자에게 의미 없는 영문 코드와 ISO 시각이 안내 문구 앞에 붙어 어색하기 때문이다. 배너는 `reason`별 문구만 보인다.
`step`은 준비 단계 오류일 때만 값이 있고, 진행 중 오류에서는 `null`이다.

### 타이머

`remainingSeconds`는 서버 시각 기준이며 총 시간에서 경과를 뺀 뒤 질문 생성 대기(답변 저장부터 다음 질문 저장까지)를 더한 값이다([공통 0013](../../shared/decisions/0013-interview-time-limit-and-early-end-report.md)). 재연결 시 클라이언트 타이머를 이 값으로 덮어쓴다.

- `thinking`을 받은 뒤 다음 메시지가 올 때까지 카운트다운을 멈춘다. 질문 음성(TTS) 재생 중에는 멈추지 않는다.
- 답변 대기 중 0이 되면 서버가 면접을 `completed`로 끝내고 `GET`·WS 연결·답변 수신 시점에 판정한다. FE는 입력과 녹음을 막고 안내한 뒤 `GET /interviews/{id}`로 상태를 다시 확인하며(서버가 아직 끝내지 않았거나 조회가 실패하면 주기적으로), `completed`면 리포트로 이동한다. 작성·녹음 중이던 답변은 저장하지 않으며, 만료 뒤 도착한 답변은 서버도 저장하지 않고 `interviewEnd`로 닫는다. 녹음을 끝내고 저장 중인 답변은 취소하지 않는다.
- 리포트: 9개 미만으로 끝난 리포트는 진행한 질문 수를 안내한다. 리포트를 만들 수 없으면(`409 report_unavailable`) 면접 조회로 시간이 끝나 진행이 짧은 면접인지 가려 안내와 다시 도전하기를 보인다.
- 마이페이지: 목록 행의 `answeredTurns`가 9 미만이면 "시간 종료 N/9턴"을, `reportAvailable`이 `false`이면 "리포트 없음"과 다시 도전하기를 보인다.

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

- 정상 완료 mock과 수신 문답의 배분이 첫 HR을 포함해 기술 6회·도메인 2회·HR 1회인지 확인하고, 첫 질문 이후 기술·도메인의 서로 다른 순서를 그대로 표시한다.
- 9번째 질문 수신만으로 완료하지 않고 답변 처리 뒤 `interviewEnd`에서 종료하며, 이탈·실패 기록에는 정상 완료 배분을 강제하지 않는다.
- 준비 4단계 체크리스트 실시간 갱신
- 준비 실패 → 면접 준비 실패 화면 전환, 실패 단계만 ✕ 표시
- `reason`·`recoverable`에 맞는 안내와 액션 표시; `question_failed`에서 FE·재연결의 임의 LLM 재시도 없음. 공통 0012의 서버 허용 복구 API와 같은 요청 ID만 사용
- 2000자 초과 → `answer_too_long` 처리, 같은 턴 재제출
- `error.reason` 분기 확인 (Sprint 1 9종)
- `onclose` 재연결 시 GET으로 세션·turns 먼저 확인; 401이면 refresh 없이 로그인 이동
- 새로고침 시 `status`별 복구 화면 확인 (`preparing_failed` 포함)
- `preparing_failed` 새로고침 시 WS 없이 `lastError`만으로 면접 준비 실패 배너 렌더 확인
- 오류·연결 종료만으로 DB 종료 상태를 바꾸지 않고, 명시적 이탈 뒤에도 저장 답변을 보존함
- `remainingSeconds` 서버값으로 동기화
- `thinking` 동안 카운트다운이 멈추고 질문 수신 뒤 다시 줄어든다. TTS 재생 중에는 계속 줄어든다.
- 답변 대기 중 0이 되면 입력이 막히고 서버가 끝낸 `completed`를 확인해 리포트로 이동한다. 녹음 중이던 답변은 저장되지 않는다.

---

## 초기 Sprint 2 참고안

아래 표는 초기 Sprint 분리 기준을 보존한다. 현재 입력·오류 처리는 뒤의 통합 서비스 계약을 따른다.

| 항목 | Sprint 1 | Sprint 2 |
| --- | --- | --- |
| 화면 구성 | 텍스트 입력창 (준비 화면 장치 점검은 선행 반영) | 녹음 컨트롤, 전사 표시 |
| 답변 전송 | `answer` 1회 (JSON) | `answerStart` → 오디오 바이너리 → `answerEnd` |
| 서버 메시지 | — | `transcript`, `questionEnd` |
| 신규 error reason | — | `stt_failed`, `tts_failed` |
| 오디오 포맷 | — | `audio/webm; codecs=opus`, 48000Hz, mono, 최대 180초 |

`answerMode`로 화면 로직을 분기하게 만들어 두면 Sprint 2 전환 시 이 값을 무시하지 않아도 된다.

질문 복구 API 성공 후 새 WS 질문이 30초 안에 오지 않으면 결과 불명으로 안내하고 같은 요청 재확인·나가기를 연다. 진행 중 요청의 새로고침에서는 GET questionRetryState의 UUID를 복원한다. 실제 검토·실행 결과는 구현 기록에서 관리한다.


## 통합 서비스의 텍스트·음성 계약

[공통 STT 0011](../../shared/decisions/0011-stt-provider-mlapi-whisper.md)과 [공통 질문 복구 0012](../../shared/decisions/0012-bounded-question-recovery.md)를 함께 따른다. 신규 면접은 `voice`를 기본값으로 사용하고 기존 면접은 저장된 `answerMode`를 유지한다. 초기 Sprint 1의 텍스트 제한은 과거 범위로 보존한다.

- `text`는 마이크 없이 입력창에서 `answer`를 전송한다. 2000자를 넘으면 같은 턴에서 수정·재제출한다.
- `voice`는 `answerStart` → 오디오 바이너리 → `answerEnd`를 전송한다. 오디오 상한을 넘으면 미완료 버퍼를 버리고 같은 질문에 다시 녹음한다.
- 서버는 입력 모드·면접 상태·답변 가능한 턴을 확인한다. 서로 다른 모드의 입력으로 STT·모델 호출이나 답변 저장을 시작하지 않는다.
- `stt_failed`의 `recoverable: true`는 같은 질문의 재답변이다. `false`와 `details.cause: "stt_unavailable"`이면 입력을 차단하고 서비스 불가를 안내한다. 서버는 소켓·기록을 유지하고, 사용자의 나가기에서 abandon을 요청한다.
- 질문 음성 재생에 실패해도 질문 텍스트를 표시한다. HTTP 동사 등 발음 보정은 표시 원문을 변경하지 않는다.
- 질문·리포트의 `turns`는 `mainIndex`와 `followUpDepth`를 함께 제공한다. 메인은 깊이 0이며 꼬리질문은 같은 메인 순번을 유지한다.
- 질문 이어가기는 서버가 허용한 범위에서 요청 UUID 하나를 유지한다. 결과를 모르는 재시도·새로고침도 같은 UUID를 재확인하며 답변을 재전송하지 않는다. `crypto.randomUUID`가 없으면 `crypto.getRandomValues`로 UUID v4를 생성한다.

실제 실행·검증 결과는 [AI 구현 기록](../../ai/implementation.md)에 모아 기록한다.
