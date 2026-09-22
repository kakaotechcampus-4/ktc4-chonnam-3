# 준비 재시도 전송 방식 — REST 확정

상태: Proposed
작성일: 2026-09-22
제안: FE
결정 필요: BE (수락 시 `spec/shared/decisions/`에 기록하고 `migration.md` 행을 FIX로 확정)

## 배경

준비 실패 후 "다시 시도"의 전송 방식이 문서마다 다르다.

| 위치 | 방식 |
| --- | --- |
| `spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md:32` | REST `POST /interviews/{id}/prepare/retry` (Accepted, 2026-09-15) |
| `spec/frontend/features/interview.md:101`·`:156`, `spec/backend/features/interview.md:45` | REST |
| `backend/docs/api-spec.md:25`, `backend/docs/task-13-interview-rest.md:18` | REST |
| `frontend/docs/api-spec.md:1142` | WS `{ "type": "prepareRetry" }` (2026-09-10) |
| `spec/shared/contracts/openapi.yaml` | 없음 |

`openapi.yaml:10-11`이 WS를 `frontend/docs/api-spec.md`에 위임하므로 WS 계약 원본은 api-spec.md다.
따라서 `migration.md:9`의 "계약 원본 = openapi.yaml"만으로는 이 충돌이 풀리지 않는다.

다만 `0010`은 Accepted이고 `:95`에서 "FE 문서의 `prepareRetry` WS 메시지 ... Sprint 1 기준으로
정정한다"고 이미 지시하고 있다. 즉 미합의 충돌이 아니라 **Accepted 결정이 FE 문서에 미반영**된 상태다.
이 문서는 그 결정을 재확인하고, 기술적 근거와 반영 범위를 정리한다. BE에는 구현 확인만 요청한다.

## 결론

REST `POST /interviews/{id}/prepare/retry`로 확정한다. `frontend/docs/api-spec.md`의 WS
`prepareRetry` 클라이언트 메시지를 제거한다. Sprint 1 WS 클라이언트 메시지는 `answer` 하나만 남는다.

## 근거

WS안과 REST안을 같은 기준으로 비교한 결과다.

| 항목 | WS `prepareRetry` | REST |
| --- | --- | --- |
| 소켓 열린 경로 (진행 중 실패) | `send` 한 줄 | `fetch` 한 줄 — 동급 |
| 새로고침 후 실패 화면 | 소켓 열고 `onopen`까지 기다렸다 전송하는 래치 필요 | 요청 성공 후 연결. 유실 경로 없음 |
| 재시도 거절 (이미 재실행 중) | 표현 수단 없음. `error.reason` 신설 필요 | reason 신설 필요하나 상태코드는 `backend/docs/error-reasons.md`의 409 선례를 그대로 쓴다 |
| 세션 소멸 | 핸드셰이크 실패로만 간접 확인 | `410` (`run_expired` 선례) |
| 만료 토큰 복구 | 불가. 연결 유지 중 토큰 만료는 감지 불가 (`api-spec.md:1135`) | 401 인터셉터로 갱신 후 재요청 |
| 재시도 직후 이벤트 갭 | 없음 | 있음 — 아래 참조 |

마지막 한 줄을 제외하면 REST가 유리하다. 거절·소멸은 양쪽 다 이름을 하나 신설해야 하지만,
REST는 상태코드 선례를 그대로 쓰고 WS는 메시지 계약을 늘려야 한다.

rate limit 대기 시간은 이 비교에서 뺐다. 전송 방식과 무관한 별개 구멍이므로 아래 "미해결"에 적는다.

### 소켓은 닫지 않는다

REST 요청과 WS는 별개 커넥션이다. 재시도할 때 소켓을 끊었다 다시 열지 않는다.

- 소켓이 열려 있으면: 그대로 두고 `POST`만 보낸다. 재실행 진행은 같은 소켓의 `prepareStep`으로 온다.
- 소켓이 없으면 (`preparing_failed`로 마운트된 경우): `POST` 성공을 확인한 뒤 소켓을 연다.

REST 응답보다 `prepareStep: running`이 먼저 도착할 수 있으나 문제가 되지 않는다. `POST`가 실패하면
재실행이 시작되지 않으므로 "요청 실패인데 진행 이벤트가 온다"는 모순은 생기지 않는다.

### 유일한 손해 — 이벤트 갭

소켓이 없는 경로에서 `POST` 성공과 WS 연결 수립 사이에 발행된 `prepareStep`을 놓칠 수 있다.
현재 보정은 연결 전 `GET /interviews/{id}` 스냅샷인데, 여기에는 `lastError`만 있고 단계별 진행
상태가 없다.

Sprint 1 범위에서는 재시도 직후 모든 단계가 `pending`/`running`이라 실제 손실이 작다. 필요하면
WS 연결 직후 서버가 현재 `prepareStep` 상태를 다시 발행하는 방식으로 보완한다. 이 보완은 재시도
전송 방식과 독립이므로 이 문서에서 결정하지 않는다.

## 계약 추가 — `POST /interviews/{id}/prepare/retry`

이 저장소는 상태코드를 먼저 정하지 않는다. `backend/docs/error-reasons.md:20-45`가 reason별
HTTP 표를 갖고 있고, reason이 정해지면 상태코드가 표에서 따라온다. 아래도 그 순서로 적는다.

### 실패 응답

| 상황 | reason | HTTP | 근거 |
| --- | --- | --- | --- |
| 이미 재실행 중 | `prep_in_progress` (신설) | 409 | 분석 쪽 `run_in_progress` 409 선례 |
| `preparing_failed` 상태가 아님 | `prep_failed` (기존) | 409 | `error-reasons.md:39` |
| 세션 소멸 | 면접 쪽에 대응 항목 없음 (신설) | 410 | 분석 쪽 `run_expired` 410 선례 |
| 미인증 | `unauthenticated` | 401 | `error-reasons.md:22` |

rate limit은 이 표에 넣지 않는다. 재시도 요청은 워커 작업을 큐에 넣고 바로 반환하며 GitHub
호출은 그 뒤 워커의 `analyze_repo`에서 일어난다. 한도 초과는 요청 응답이 아니라 WS `error`
(`github_api_rate_limited`)로 도착하므로 이 엔드포인트의 응답 코드 문제가 아니다.

### 성공 응답

재실행 수락은 비동기이므로 202가 자연스럽다. 다만 이 `openapi.yaml`의 202는 모두 본문이 있다
(`AnalysisRunResponse`, `AnalyzingResponse`, `GeneratingResponse`). 본문 없는 202는 선례가
없으므로 형태는 BE 관례에 맞춘다. 진행 상황은 본문이 아니라 WS `prepareStep`으로 전달된다.

### 동작

서버는 실패한 `prepareStepKey`부터 재실행하고 성공한 단계는 재실행하지 않는다. 세션과
`session_repositories`는 유지한다 (`frontend/docs/api-spec.md:1151`과 동일).

## BE에 확인할 것

1. 재시도 거절 reason 두 개. `backend/docs/error-reasons.md` 표에 "이미 재실행 중"과
   "세션 소멸"에 해당하는 면접 준비 항목이 없다. 위 신설안이 맞는지 봐달라.
2. 성공 응답 형태. `frontend/src/shared/api.ts:54-55`가 204만 본문 없이 통과시키고 나머지는
   `res.json()`을 부른다. 본문 없는 202가 오면 파싱 에러로 성공 요청이 실패 처리된다.
   204로 줄지, 202에 담을 본문을 정할지 알려달라.

"재시도 후 진행 이벤트를 기존 WS 세션으로 보내는가"는 확인 항목에서 뺐다.
`frontend/docs/api-spec.md:1151`이 세션 유지를 이미 명시하고 있다.

## 수락 시 변경 대상

- `spec/shared/contracts/openapi.yaml` — `/interviews/{id}/prepare/retry` 경로 추가
- `backend/docs/error-reasons.md` — HTTP Reason 표에 재시도 거절 reason 추가
- `frontend/docs/api-spec.md` — WS 클라이언트 메시지 표에서 `prepareRetry` 제거, `:1151` 설명을 REST로 이동, `:1214-1218`·`:1560`·`:1596`의 `prepareRetry` 표기 정정, 변경 이력 추가
- `frontend/src/types/api.ts:299` — `WsClientMessage`에서 `prepareRetry` 제거
- `frontend/src/shared/api.ts` — `retryPrepare` 추가
- `frontend/src/features/interview/InterviewPrepare.tsx` — `handleRetry`를 REST 호출로 교체, `retryOnOpenRef` 제거, 거절 reason 분기 추가
- `spec/shared/contracts/migration.md` — `준비 재시도 경로` 행을 FIX로 확정

## 미해결

- 준비 실패 대기 시간을 전달할 수단이 없다. `github_api_rate_limited`의 화면 처리는 "대기 후 재시도"인데 (`spec/frontend/features/interview.md:200`), WS `error`(`frontend/docs/api-spec.md:1183`)와 `InterviewLastError`(`openapi.yaml:866`)에 `retryAfter`가 없다. 두 스키마는 "Field layout matches the WS error event"(`openapi.yaml:870-871`)로 모양을 맞추기로 되어 있어 한쪽만 고칠 수 없다. 전송 방식과 무관한 별개 항목이므로 `migration.md`에 기록하고 이 문서에서 결정하지 않는다.
- `shared/api.ts`의 401 인터셉터가 아직 구현되지 않았다. `request()`(`:27-56`)에 401 분기가 없고 `api.refresh`(`:68`)만 정의되어 있다. `InterviewPrepare.tsx:203-204`의 "GET이 401 인터셉터를 타면서 토큰이 갱신된다"는 전제가 현재는 성립하지 않는다. 재시도 전송 방식과 독립이며 별도로 처리한다.
