# FE Mock API 계층 (MSW) — 설계와 계약 검수

- 상태: Proposed
- 작성일: 2026-09-14
- 관련 브랜치: `feature/MSW_handler`
- 참조 명세: `spec/shared/contracts/openapi.yaml`, `spec/shared/contracts/migration.md`,
  `spec/backend/features/{analysis-run,documents,interview,report}.md`,
  `backend/docs/error-reasons.md`
- 검토자: FE·BE 리드 미확정

## 목적

BE 구현 전에 FE 화면을 실제 네트워크 흐름 위에서 개발할 수 있게 한다.
동시에 mock을 계약에 맞추는 과정에서 드러난 FE 코드·계약 간 차이를 기록한다.

## 범위

포함: REST 정상 흐름 핸들러, 상태 전이가 필요한 흐름(분석 run·면접 준비·리포트 생성·후보 page), SSE 스트림, fixture.

제외: 인증/권한 실패, 만료, 네트워크 실패 등 실패 케이스 전반과 WebSocket mock. 다음 작업 범위다.
`POST /reports/{id}/feedback-disagreements`는 Sprint 2이므로 핸들러를 만들지 않았다.

## 설계 결정

### 1. 계약 타입을 `src/types/contract.ts`로 분리한다

`spec/shared/contracts/README.md`는 충돌 시 `openapi.yaml`을 우선한다고 정한다.
그런데 현재 `src/types/api.ts`는 이관 전 FE 문서 기준이고, 진행 중인 화면 브랜치들이 이 타입을 쓰고 있다.

루트 `CLAUDE.md`의 "공통 계약은 전환 초안이다. migration.md의 충돌을 임의로 합의 처리하지 않는다"에 따라
`types/api.ts`를 고치지 않고, Sprint 1 FIX 계약을 `types/contract.ts`에 별도로 두었다.
mock 응답은 `HttpResponse.json<T>()`로 타입을 고정하므로, 계약이 바뀌어 타입을 수정하면 mock이 컴파일 단계에서 깨진다.

이관 합의가 끝나면 `types/api.ts`를 `types/contract.ts`로 흡수하고 이 파일을 없앤다.

### 2. 상태는 호출 횟수가 아니라 경과 시간으로 계산한다

`src/mocks/db.ts`는 `createdAt` 기준 경과 시간에서 상태를 파생한다.
SSE 스트림과 폴링 응답이 같은 값을 봐야 하는데, 호출 횟수 기반이면 둘이 어긋난다.

| 흐름 | 전이 | 기본값 |
| --- | --- | --- |
| 분석 run | step 7개 순차 진행 후 `completed` | step당 1.2초 |
| 면접 준비 | `preparing` → `in_progress` | 3.5초 |
| 리포트 | 최초 조회에서 생성 시작, 이후 `200` | 3초 |
| 후보 page | 최초 요청 `202`, 재요청 `200` | 2.5초 |

속도는 `db.ts` 상단 상수만 바꾸면 된다. seed 레코드(완료된 run 1건, 종료된 면접 1건)는 항상 존재해서
분석부터 진행하지 않고도 리포트·마이페이지 화면을 열 수 있다.

### 3. 핸들러 없는 `/api` 요청은 501로 끊는다

통과시키면 vite dev server의 SPA fallback이 `index.html`을 `200`으로 돌려주고,
화면은 JSON 대신 HTML을 받는다. 원인이 파싱 단계에서야 드러나 시간을 버린다.

`onUnhandledRequest: 'warn'`은 콘솔 경고만 남기고 요청은 그대로 통과시킨다.
그래서 핸들러 배열 마지막에 catch-all을 두고 `501`과 함께 누락된 경로를 콘솔에 찍는다.
실제 서버는 501을 쓰지 않으므로 이 응답은 mock 누락이라는 뜻으로만 읽으면 된다.

### 4. 개발 서버에서는 기본으로 켠다

`.gitignore`가 `.env*`를 제외하므로 옵트인 방식은 팀원마다 파일을 따로 만들어야 한다.
BE가 아직 없는 시점이라 `import.meta.env.DEV`에서 기본 on으로 두고,
끄려면 각자 `frontend/.env.local`에 `VITE_USE_MSW=false`를 넣는다. 시작 시 콘솔에 사용 중임을 알린다.

프로덕션 번들에는 들어가지 않는다(빌드 산출물에서 mock 코드·fixture 문자열 0건 확인).
`public/mockServiceWorker.js`는 `dist/`에 복사되지만 이를 시작시키는 코드가 번들에 없어 동작하지 않는다.

## 계약 검수 — 확인이 필요한 항목

### A. `types/api.ts`와 `openapi.yaml`의 차이

mock은 `openapi.yaml`을 따랐다. 해당 화면을 구현하기 전에 `types/api.ts` 이관 여부를 정해야 한다.

| 항목 | `types/api.ts` (이관 전) | `openapi.yaml` (Sprint 1 FIX) |
| --- | --- | --- |
| `POST /analysis-runs` | `multipart/form-data`, `jobUrl` + 파일 | JSON `{ postingUrl, documentId }` |
| 파일 업로드 | 이 엔드포인트에 포함 | `POST /documents/preview`로 분리 |
| `StepKey` | 4개 | 7개 |
| `StepStatus` | `completed` | `succeeded` / `failed` 추가 |
| 진행률 | `estimatedSeconds` | `progress` (0~100) |
| 결과 응답 | `position`, `jdRequirements` | `analyzedCount`, `failedCount`, `failedRepositories` |
| repo 식별자 | `id`, `name` | `repositoryId`, `fullName`, `name` |
| 후보 더 보기 | 없음 | `GET /analysis-runs/{runId}/candidates?page=N` |
| 페르소나 | `AgentRole` (`senior_developer`, `manager`) | `Persona` (`hr_manager`, `domain_lead`) |
| 턴·피드백 필드 | `role` | `persona` |
| `InterviewStatus` | 3개 | `preparing`, `preparing_failed` 추가 |
| 이의 제기 API | 있음 | Sprint 2 (계약에 없음) |

`src/shared/api.ts`의 `createAnalysisRun(formData)`는 현재 계약과 맞지 않는다.
해당 화면이 아직 없어 동작에는 영향이 없으나, mock은 multipart 요청에 501과 안내 메시지를 돌려주도록 해 두었다.

### B. `openapi.yaml`에 정의가 없어 mock이 가정한 항목

| 항목 | mock의 가정 | 필요한 확인 |
| --- | --- | --- |
| SSE 이벤트 payload | `{type:'step'\|'completed'\|'failed'}`에 새 enum 적용 | 계약은 `text/event-stream`만 정의. BE 실제 형식 확인 필요 |
| `/interviews/{id}/retry` 404 | 없는 면접에 `404 not_found` | 계약의 응답 목록에 404가 없음 |
| `POST /interviews`의 없는 `runId` | `400 invalid_repository` + `details.runId` | 계약에 404/410이 없어 400으로 처리 |
| 면접 제한 시간 | `remainingSeconds` 900초 시작 | 계약에 값 근거 없음 |
| 리포트 score key/label | 기존 6개 유지 | `score_criteria` 시드와 산정 방식은 `PENDING_TEAM` |

### C. 화면에 필요하지만 계약에 없는 필드

`openapi.yaml`의 응답 스키마에는 아래 필드가 없다. 현재 mock은 계약대로 내려주지 않는다.

- `InterviewDetailResponse`: `position`, `repositoryNames` — 면접 진행·준비 화면 헤더에 쓰던 값.
- `ReportResponse`: `position`, `headline`, `summary`, `repositoryNames`, `completedAt` — 리포트 화면 상단 구성 요소.

화면에서 빼거나 계약에 추가하거나 둘 중 하나를 정해야 한다.

### D. 아직 이관되지 않은 엔드포인트

`GET /me/home`, `GET /me/interviews`, `POST /auth/logout`은 `openapi.yaml`에 없다.
`migration.md` 기준으로 `GET /me`와 에러 envelope만 이관됐다.
mock은 이 세 개를 `frontend/docs/api-spec.md` 기준으로 두고 응답 타입도 `types/api.ts`를 쓴다.
홈·마이페이지 화면이 이미 진행 중이므로 이관 우선순위가 높다.

### E. `PENDING_FE` 항목에 대한 mock의 임시 처리

임의 확정이 아니라 mock이 동작하기 위한 최소 가정이다. 결정은 FE 논의 대상이다.

- WS 식별자: `POST /interviews` 응답에 `interviewId`와 `sessionId`를 모두 내려준다. 화면은 `interviewId`만 쓰도록 한다.
- `preparing_failed`: 상태값은 타입에 두되 mock은 아직 이 상태를 만들지 않는다.
- `questionEnd`, 이탈/복구, JWT 전달: WS 작업에서 다룬다.

## 기존 FE 인프라 검토

mock을 붙이면서 확인한 항목이다. 이번 변경에는 포함하지 않았다.

| # | 항목 | 내용 |
| --- | --- | --- |
| 1 | `/api` proxy 부재 | `vite.config.ts`에 proxy가 없다. mock이 가려 주는 동안은 드러나지 않고, 실서버 연동 시점에 터진다. BE와 prefix 규약 합의 필요 |
| 2 | 리포트 `202` 분기 없음 | `request()`는 `res.ok`면 본문을 그대로 반환한다. `202 { status:'generating' }`이 `ReportResponse`로 취급된다 |
| 3 | mutation 에러 전역 처리 없음 | `providers.tsx`에 `QueryCache.onError`만 있어 `useMutation` 실패의 401은 잡히지 않는다 |
| 4 | 4xx 재시도 | `retry: 1`이 401·409에도 적용된다 |
| 5 | `/login` 리다이렉트 | 로그인 화면에서 401이 나면 같은 경로로 다시 이동한다 |
| 6 | CORS·쿠키 미검증 | MSW는 CORS를 거치지 않는다. `credentials: 'include'` + 별도 오리진 조합은 실서버에서 처음 검증된다 |
| 7 | 워커 시작 실패 시 빈 화면 | 이번 작업 중 실제로 재현했다. `main.tsx`의 bootstrap이 throw하면 `render()`까지 가지 않아 화면이 통째로 비고 콘솔 에러만 남는다. 시크릿 창·브라우저 설정·확장 프로그램으로도 발생할 수 있어 이번 변경에서 try/catch로 감싸 mock 없이도 앱은 뜨게 했다 |

## 검증

테스트 도구가 없으므로 `spec/frontend/verification.md`에 따라 수동 시나리오와 결과를 기록한다.
브라우저에서 개발 서버(`npm run dev`)를 띄우고 페이지 컨텍스트에서 `fetch`/`EventSource`로 확인했다.
재현 절차는 `frontend/docs/msw-smoke-check.js`로 남겼다. 마지막 실행 결과는 31건 전부 통과다.

| 시나리오 | 기대 | 결과 |
| --- | --- | --- |
| `GET /me`, `GET /me/home`, `GET /me/interviews` | 200 | 통과 |
| `POST /auth/logout` | 204 | 통과 |
| 홈 시나리오 전환 (localStorage·쿼리) | `completed`/`no_interview`/`no_repository` | 통과 |
| `POST /analysis-runs` JSON | 202, `runId` | 통과 |
| 같은 공고 재요청 | 기존 `runId` + `reused: true` | 통과 |
| 원티드 외 URL | 400 `unsupported_site` | 통과 |
| multipart로 호출 | 501 + 계약 안내 | 통과 |
| 분석 진행 폴링 | `progress` 0→100, step 7개 전이 | 통과 |
| 완료 전 `/result` | 409 `not_ready` | 통과 |
| SSE `/events` | step 14건 + `completed`, 스트림 종료 | 통과 |
| 완료 후 `/result` | 200, `analyzedCount 5` / `failedCount 1` | 통과 |
| `/candidates?page=2` | 최초 202 `analyzing`, 재요청 200 | 통과 |
| `POST /documents/preview` | 200, GitHub URL 3건 | 통과 |
| `.hwp` 업로드 | 415 `unsupported_document_type` | 통과 |
| repo 0개 선택 | 400 `no_repository_selected` | 통과 |
| 분석 실패 repo 선택 | 400 `invalid_repository` + `details` | 통과 |
| `POST /interviews` | 201, `interviewId`·`sessionId` | 통과 |
| 활성 면접 중복 생성 | 409 `session_limit_exceeded` | 통과 |
| 면접 준비 → 진행 | `preparing`(턴 0) → `in_progress`(1턴, `hr_manager`) | 통과 |
| 진행 중 면접의 리포트 | 409 `report_unavailable` | 통과 |
| 종료된 면접의 리포트 | 1차 202 `generating`, 2차 200 (9턴·6점수·3페르소나) | 통과 |
| 없는 면접 조회 | 404 `not_found` | 통과 |
| 미등록 `/api` 경로 | 501 + 콘솔 에러 | 통과 |
| 정적 자산 요청 | 그대로 통과, 경고 없음 | 통과 |
| `npm run lint`, `npm run build` | 통과 | 통과 (동작 테스트 아님) |
| 프로덕션 번들에 mock 포함 여부 | 미포함 | 통과 (`dist` 검색 0건) |

미실행: 자동화 테스트(도구 미선정), WebSocket, 실패 케이스 전반, 실서버 연동.

## 후속

1. A의 계약 이관 여부 결정 — 화면 구현보다 먼저 필요하다.
2. C의 누락 필드를 화면에서 뺄지 계약에 추가할지 결정.
3. D의 세 엔드포인트 이관.
4. B의 SSE payload 형식을 BE와 확정.
5. 실패 케이스 핸들러와 WS mock (다음 작업).
