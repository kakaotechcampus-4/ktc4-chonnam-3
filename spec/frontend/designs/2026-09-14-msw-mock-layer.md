# FE Mock API 계층 (MSW) — 설계와 계약 검수

- 상태: Accepted
- 작성일: 2026-09-14
- 개정: 2026-09-19 — PR #28 멘토 리뷰 반영, `openapi.yaml` 단일 원본 기준으로 재정렬
- 관련 브랜치: `feature/MSW_handler` → `refactor/mocks`
- 참조 명세: `spec/shared/contracts/openapi.yaml`, `spec/shared/contracts/migration.md`,
  `spec/backend/features/{analysis-run,documents,interview,report}.md`,
  `backend/docs/error-reasons.md`
- 검토자: FE·BE 리드 미확정

## 목적

BE 구현 전에 FE 화면을 실제 네트워크 흐름 위에서 개발할 수 있게 한다.
동시에 mock을 계약에 맞추는 과정에서 드러난 FE 코드·계약 간 차이를 기록한다.

## 범위

포함: REST 정상 흐름 핸들러, 상태 전이가 필요한 흐름(분석 run·면접 준비·리포트 생성·후보 page), SSE 스트림, fixture.

`openapi.yaml`의 operation 16개 전부에 핸들러가 있다. SSE 스트림은 계약 밖(`api-spec.md` #13)이라 별도로 둔다.

제외: 인증/권한 실패, 만료, 네트워크 실패 등 실패 케이스 전반과 WebSocket mock. 다음 작업 범위다.
WS(`/ws/interviews/{sessionId}`)는 `InterviewPrepare`·`InterviewScreen`이 아직 스텁이라 소비처가 없어 화면 작업과 함께 한다.

## 설계 결정

### 1. 계약 타입은 `src/types/api.ts` 하나만 쓴다 (2026-09-19 개정)

**초판 결정(계약 타입을 `src/types/contract.ts`로 분리)은 폐기했다.**

초판은 `types/api.ts`가 이관 전 FE 문서 기준이라 임의로 고칠 수 없다고 보고 Sprint 1 계약을
`types/contract.ts`에 따로 두었다. 그 전제가 사라졌다. 커밋 `3143c75`·`81894a0`에서
`openapi.yaml`을 유일 원본으로 확정하고 `types/api.ts`와 전수 대조를 마쳤다.

남은 문제는 mock만 `contract.ts`를 본다는 것이었다. 실제로 PR #28에서 런타임 오류로 드러났다.
`/result` 목이 `jdRequirements`를 빠뜨려 `RepoSelect`가 dev에서만 깨졌다(멘토 리뷰 `4040570820`).
원본이 둘이면 둘이 어긋나고, 어긋난 쪽을 쓰는 코드가 먼저 깨진다.

그래서 `types/contract.ts`를 삭제하고 `src/mocks/**` 전체가 `types/api.ts`를 쓴다.
mock 응답은 `HttpResponse.json<T>()`로 타입을 고정하므로, 계약이 바뀌어 타입을 고치면
어긋난 mock이 `tsc -b` 단계에서 드러난다. 이 리팩터링 자체가 그 방식으로 진행됐다.

부수 변경으로 `ApiError`를 둘로 나눴다. 네트워크 본문은 `ApiErrorBody`(계약의 `ApiError` 스키마와 1:1,
`details` 포함), 클라이언트가 HTTP 상태코드를 덧붙인 형태가 `ApiError`다. 목은 본문 타입만 쓴다.

### 2. 상태는 호출 횟수가 아니라 경과 시간으로 계산한다

`src/mocks/db/`는 `createdAt` 기준 경과 시간에서 상태를 파생한다.
(초판의 단일 `db.ts`는 300줄을 넘겨 `config.ts`·`runs.ts`·`interviews.ts`로 나누고 `index.ts`에서 다시 내보낸다.)
SSE 스트림과 폴링 응답이 같은 값을 봐야 하는데, 호출 횟수 기반이면 둘이 어긋난다.

| 흐름 | 전이 | 기본값 |
| --- | --- | --- |
| 분석 run | step 7개 순차 진행 후 `completed` | step당 1.2초 |
| 면접 준비 | `preparing` → `in_progress` | 3.5초 |
| 리포트 | 최초 조회에서 생성 시작, 이후 `200` | 3초 |
| 후보 page | 최초 요청 `202`, 재요청 `200` | 2.5초 |

속도는 `db/config.ts` 상수만 바꾸면 된다. seed 레코드는 항상 존재해서 분석부터 진행하지 않고도 화면을 열 수 있다.

| seed | 상태 | 여는 화면 |
| --- | --- | --- |
| `SEED_RUN_ID` | 완료된 run | 5a-v2 레포 선택 |
| `SEED_FAILED_RUN_ID` | 실패한 run (`jd_fetch` 에서 중단) | 3-3 분석 실패 |
| `SEED_INTERVIEW_ID` | 종료된 면접 | 5c-v2 리포트, 마이페이지 |
| `SEED_PREPARING_FAILED_INTERVIEW_ID` | `preparing_failed` + `lastError` | 1b 면접 준비 실패 |

뒤의 두 건은 2026-09-19 개정에서 추가했다. 초판에는 `failed` run을 만들 방법이 없어
`AnalysisFailed` 화면을 열 수 없었고, SSE의 `failed` 분기는 실행되지 않는 죽은 코드였다.

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

## 계약 검수 (2026-09-19 개정)

초판의 A~E 항목은 대부분 해소됐다. 무엇이 어떻게 정리됐는지 남긴다.

### A. 해소됨 — `types/api.ts`와 `openapi.yaml`의 차이

초판 시점에는 둘이 달랐다. 지금은 일치한다(커밋 `3143c75`·`81894a0`).
초판 표에서 "openapi.yaml 쪽"으로 적었던 값 중 실제로는 반대로 확정된 것이 있으니 주의한다.

| 항목 | 초판 표의 기술 | 2026-09-19 확정값 |
| --- | --- | --- |
| repo 식별자 | `repositoryId` | **`id`** |
| `StepStatus` 완료 | `succeeded` | **`completed`** (+ `skipped`) |
| 결과 응답 | `analyzedCount`·`failedCount`·`failedRepositories` | **`position`·`jdRequirements`·`mentionedRepoCount`·`matchedRepoCount`** |
| 이의 제기 API | Sprint 2, 계약에 없음 | **계약에 있음** — `POST /interviews/{id}/feedback-disagreements` |

`POST /analysis-runs`가 JSON이라는 점, `StepKey` 7개, `Persona` 3종은 초판대로 유지됐다.
`shared/api.ts`의 multipart 호출은 이미 JSON으로 고쳐졌다. mock의 multipart 501 가드는 회귀 감지용으로 남긴다.

### B. 일부 해소 — `openapi.yaml`에 정의가 없어 mock이 가정한 항목

| 항목 | 현재 처리 | 상태 |
| --- | --- | --- |
| SSE 이벤트 payload | `{type:'step'\|'completed'\|'failed'}` — `api-spec.md` #13 기준 | **미해결(D7)** — BE 구현과 대조 필요 |
| SSE `progress` 이벤트 | **전송하지 않는다** | 읽는 화면이 하나도 없어 계약 쪽을 정리하기로 함(리뷰 `4050021937`, 커밋 `e25d68e`) |
| 없는 리소스 조회 | `/analysis-runs/*`는 `410 run_expired`, `/interviews/{id}`는 `404 not_found` | **부분 해결(D3)** — 계약의 응답 목록에 맞춰 410으로 옮겼다. `retry`·`report`의 404는 계약에 없어 남아 있다 |
| `POST /analysis-runs` 중복 | `409 run_in_progress` + `details.runId` | 초판의 `reused: true` 본문 필드를 버렸다. 계약 응답에 그런 필드가 없다(D2) |
| 면접 제한 시간 | 900초 | **미해결(D5)** — 계약에 근거 없음 |
| 리포트 score key/label | 6개 유지 | **미해결(D6)** — 산정 방식 `PENDING_TEAM` |

### C. 해소됨 — 화면에 필요하지만 계약에 없던 필드

`InterviewDetailResponse`에 `position`·`repositoryNames`·`runId`·`answerMode`·`companyName`·`lastError`가,
`ReportResponse`에 `position`·`positionLabel`·`headline`·`summary`·`coverage`·`repositoryNames`·`completedAt`가
계약에 추가됐다. mock이 전부 채워 내려준다.

`ReportCoverage.uncoveredRequirements`는 화면(`Report.tsx`)이 `join(', ')`으로 그대로 출력하므로
id가 아니라 요구사항 `text`를 담는다.

### D. 해소됨 — 이관되지 않았던 엔드포인트

`GET /me/home`, `GET /me/interviews`, `POST /auth/logout`은 모두 `openapi.yaml`에 있다.
`GET /me/profile`과 `POST /auth/refresh` 핸들러를 새로 만들었다.
**`/me/profile`은 핸들러가 없어 마이페이지가 catch-all 501에 걸려 깨져 있었다.**

`GET /me/interviews`의 `status` 쿼리 파라미터는 팀에 제안만 된 상태다(리뷰 `4050406821`).
계약에 없으므로 mock에 넣지 않고 `handlers/user.ts`에 `TODO(contract)`로 남겼다.

### E. `PENDING_FE` 항목에 대한 mock의 처리

- WS 식별자: `CreateInterviewResponse`가 `sessionId`·`interviewId` 둘 다 required로 확정됐다.
  라우트 `:id`는 `interviewId`, WS 경로는 `sessionId`다.
- `preparing_failed`: `lastError`가 계약에 들어와 seed로 이 상태를 만들 수 있게 됐다.
- `questionEnd`, 이탈/복구, JWT 전달: WS 작업에서 다룬다.

### F. 픽스처 내부 정합 (신규)

레포 카드의 `matchedRequirementIds`가 존재하지 않는 요구사항 id를 가리키고 있었다.
타입 검사로는 잡히지 않고 화면의 매칭 표시만 조용히 비는 종류의 오류다.
`fixtures/jd.ts`에 요구사항을 신설하고 카드가 그 상수를 참조하게 했다.
스모크 스크립트가 고아 참조 0건을 검사한다.

## 기존 FE 인프라 검토

mock을 붙이면서 확인한 항목이다. 이번 변경에는 포함하지 않았다.

| # | 항목 | 내용 |
| --- | --- | --- |
| 1 | `/api` proxy 부재 | `vite.config.ts`에 proxy가 없다. mock이 가려 주는 동안은 드러나지 않고, 실서버 연동 시점에 터진다. BE와 prefix 규약 합의 필요 |
| 2 | ~~리포트 `202` 분기 없음~~ | 해소됨 — `Report.tsx`가 `'status' in data`로 분기하고 `retryAfter` 간격으로 재조회한다. 다만 탭이 포커스를 잃으면 폴링이 멈춘다(위 「검증 중 관찰한 것」) |
| 3 | mutation 에러 전역 처리 없음 | `providers.tsx`에 `QueryCache.onError`만 있어 `useMutation` 실패의 401은 잡히지 않는다 |
| 4 | 4xx 재시도 | `retry: 1`이 401·409에도 적용된다 |
| 5 | `/login` 리다이렉트 | 로그인 화면에서 401이 나면 같은 경로로 다시 이동한다 |
| 6 | CORS·쿠키 미검증 | MSW는 CORS를 거치지 않는다. `credentials: 'include'` + 별도 오리진 조합은 실서버에서 처음 검증된다 |
| 7 | 워커 시작 실패 시 빈 화면 | 이번 작업 중 실제로 재현했다. `main.tsx`의 bootstrap이 throw하면 `render()`까지 가지 않아 화면이 통째로 비고 콘솔 에러만 남는다. 시크릿 창·브라우저 설정·확장 프로그램으로도 발생할 수 있어 이번 변경에서 try/catch로 감싸 mock 없이도 앱은 뜨게 했다 |

## 검증 (2026-09-19 실행)

테스트 러너가 없으므로(`package.json`에 `test` 스크립트 부재) `spec/frontend/verification.md`에 따라
수동 시나리오로 확인한다. 재현 절차는 `frontend/docs/msw-smoke-check.js`에 있다.

### 실행한 명령

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| frontend | `npx tsc -b --force` | 통과 (오류 0) |
| frontend | `npm run lint` | 통과 (경고 0) |
| frontend | `npm run build` | 통과 (85 모듈) |

`tsc -b`가 이번 리팩터링의 주 안전망이었다. `contract.ts`를 지우자 어긋난 목이 전부 컴파일 오류로 드러났다.

### 스모크 스크립트

`npm run dev` 후 브라우저 콘솔에서 `frontend/docs/msw-smoke-check.js` 실행.
**59건 전부 통과.** 응답 필드는 계약의 required 집합과 키 단위로 대조한다.

초판의 "SSE 이벤트 15건" 검사는 뺐다. 구독 시점에 따라 이미 지나간 step의 `running`을 못 받아
개수가 흔들린다. 대신 "step 7개가 모두 종료 상태로 도착"·"`succeeded` 미사용"·"`progress` 0건"을 본다.

### 화면 시나리오

| # | 시나리오 | 결과 |
| --- | --- | --- |
| V1 | `/mypage` — 이름·희망직무·GitHub·면접 이력 렌더 | 통과 (이전에는 `/me/profile` 501로 깨짐) |
| V2 | `/interview/repos/{SEED_RUN_ID}` — JD 요구사항 3분류 + 포트폴리오 안내 문구 | 통과 (멘토가 지적한 `jdRequirements.filter` 오류 해소) |
| V3 | 파일명에 `fail` 포함 업로드 → `extractStatus: 'failed'` | 통과 |
| V4 | `documentId` 없이 분석 시작 → `doc_extract: skipped`, 체크리스트 1행 ✓ | 통과 |
| V5 | JobInput → analyzing → repos 전체 흐름 | 통과 |
| V6 | 완료된 run 재진입 시 스냅샷만으로 즉시 이동 | 통과 |
| V7 | `/interview/failed/{SEED_FAILED_RUN_ID}` — ✓/✓/!/대기 | 통과 |
| V8 | seed 면접 리포트 — headline·summary·coverage·positionLabel·6점수·3피드백 | 통과 |
| V9 | `/candidates?page=2` 202 → 200, `page` 누락 시 400 | 통과 |
| V10 | 6개 화면 순회 시 `[msw] 핸들러가 없는 요청` 로그 | 0건 |
| V11 | `dist/`에 mock 문자열 | 0건 |

### 미실행

자동화 테스트(도구 미선정), WebSocket, 인증 실패 케이스 전반, 실서버 연동, CORS·쿠키.

### 검증 중 관찰한 것 (이번 변경 범위 밖)

리포트 화면의 `refetchInterval` 폴링이 탭이 포커스를 잃으면 멈춘다(TanStack Query 기본 동작).
202 `generating` 상태에서 탭을 두면 200이 된 뒤에도 "리포트를 만들고 있어요"에 머문다.
`refetchIntervalInBackground: true`가 필요한지는 화면 담당자가 판단할 일이라 손대지 않았다.

## 팀 결정이 필요한 항목

mock이 임의로 확정하지 않았다. 루트 `CLAUDE.md`의 "migration.md의 충돌을 임의로 합의 처리하지 않는다"를 따른다.

| # | 항목 | 현재 mock | 필요한 결정 |
| --- | --- | --- | --- |
| D1 | `POST /documents/preview`의 `file` 필드 누락 | `400 internal_error` | 400을 계약에 추가할지, 415로 흡수할지 |
| D2 | `POST /analysis-runs` 중복 요청 | `409 run_in_progress` + `details.runId` | 이 형태로 계약에 명시할지 (`api-spec.md` #11은 이미 이 형태) |
| D3 | `retry`·`report`의 없는 리소스 | `404 not_found` | 계약 응답 목록에 404가 없다. 410으로 옮길지 계약에 404를 추가할지 |
| D4 | 핸들러 없는 `/api` 경로 | `501` | 실서버가 안 쓰는 코드를 mock 신호로 쓰는 것이 괜찮은지 (멘토 질문 미회신) |
| D5 | 면접 제한 시간 900초 | 상수 | `spec/backend/features/interview.md`에 근거 명시 필요 |
| D6 | 점수 산정 | fixture 예시값 | `PENDING_TEAM` |
| D7 | SSE payload 형식 | `api-spec.md` #13 기준 | BE 구현과 대조 |
| D8 | SSE `progress` 이벤트 | 미전송 | 계약에서 제거할지 결정 후 `api-spec.md`·`types/api.ts`의 `SseProgressEvent` 정리 |

## 후속

1. D1~D8 결정.
2. 실패 케이스 핸들러 (인증 실패·만료·네트워크 실패).
3. WS mock — `InterviewPrepare`·`InterviewScreen` 화면 작업과 함께.
4. `/me/interviews?status=` 가 합의되면 목에 반영.
5. 테스트 러너 선정 — 지금의 수동 스모크 스크립트를 자동 테스트로 옮긴다.
