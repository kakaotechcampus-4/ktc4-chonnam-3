# 작업 07 — MSW mock API

> 선행: task-06 완료
> 설계·계약 검수 기록: [`spec/frontend/designs/2026-09-14-msw-mock-layer.md`](../../spec/frontend/designs/2026-09-14-msw-mock-layer.md)

## 목표

BE 없이 화면을 개발할 수 있도록 Service Worker 기반 mock API를 붙인다.
응답은 `spec/shared/contracts/openapi.yaml`(Sprint 1 FIX)을 기준으로 한다.

## 1. 설치

```bash
npm i -D msw
npx msw init public --save
```

`public/mockServiceWorker.js`가 생기고 `package.json`에 `msw.workerDirectory`가 기록된다. 둘 다 커밋한다.

## 2. 폴더 구조

```
src/mocks/
├─ browser.ts            setupWorker
├─ start.ts              워커 시작 (동적 import 전용)
├─ db.ts                 상태를 가진 in-memory 저장소
├─ http.ts               경로·에러 envelope·시나리오 스위치
├─ handlers/
│  ├─ index.ts           핸들러 집합 + 미등록 경로 catch-all
│  ├─ user.ts            /me, /me/home, /me/interviews, /auth/logout
│  ├─ documents.ts       /documents/preview
│  ├─ analysis.ts        /analysis-runs (+ SSE, result, candidates)
│  └─ interview.ts       /interviews (+ report, retry)
└─ fixtures/             도메인별 응답 데이터
src/types/contract.ts    Sprint 1 FIX 계약 타입
```

## 3. 실행

```bash
npm run dev
```

개발 서버에서 기본으로 켜진다. 콘솔에 `[msw] mock API 사용 중 (/api/*)`가 찍힌다.

끄려면 `frontend/.env.local`(git 추적 제외)에 다음을 넣는다.

```
VITE_USE_MSW=false
```

## 4. 핸들러 확인하기

### 워커가 붙었는지

`npm run dev` 후 브라우저 콘솔에 두 줄이 보이면 정상이다.

```
[MSW] Mocking enabled.
[msw] mock API 사용 중 (/api/*)
```

안 보이면 devtools → Application → Service Workers에서 `mockServiceWorker.js`가 activated인지 본다.
등록에 실패해도 앱은 뜨고 콘솔에 실패 사유가 찍힌다. 이때 `/api` 요청은 dev server로 넘어가 `index.html`을 받는다.

### 전체 흐름 한 번에

[`docs/msw-smoke-check.js`](msw-smoke-check.js) 전체를 devtools 콘솔에 붙여넣는다.
등록된 핸들러를 순서대로 호출하고 PASS/FAIL 표를 출력한다. 약 15초 걸린다.

```
전체 31 · PASS 31 · FAIL 0
```

mock 상태가 메모리에 남으므로 페이지당 한 번만 유효하다. 다시 돌리려면 새로고침한다.

### 개별 요청

Network 탭에서 요청을 고르면 MSW가 처리한 응답을 그대로 볼 수 있다. 콘솔에서 직접 불러도 된다.

```js
await (await fetch('/api/me/home')).json();
await (await fetch('/api/analysis-runs/5c7b9e10-0000-4000-8000-00000000aaaa/result')).json();
```

핸들러가 없는 경로는 501과 함께 콘솔에 `[msw] 핸들러가 없는 요청: GET /api/...`이 찍힌다.
이 501이 보이면 서버 오류가 아니라 mock 누락이다.

## 5. 시나리오 전환

정적 응답을 바꿔 끼우는 엔드포인트는 쿼리스트링이나 `localStorage`로 전환한다.
우선순위는 `?scenario=` > `localStorage` > 기본값이다.

| 대상 | 키 | 값 |
| --- | --- | --- |
| `GET /me` | `msw.me` | `linked`(기본) · `unlinked` |
| `GET /me/home` | `msw.home` | `completed`(기본) · `no_interview` · `no_repository` |

```js
// devtools 콘솔
localStorage.setItem('msw.home', 'no_repository');
```

문서 preview는 파일명으로 결과가 갈린다. 이름에 `partial`이 들어가면 `partial`, `fail`이 들어가면 `failed`다.

## 6. 시간이 지나야 바뀌는 흐름

`src/mocks/db.ts`가 `createdAt` 기준 경과 시간으로 상태를 계산한다. 속도는 파일 상단 상수로 조정한다.

| 흐름 | 동작 |
| --- | --- |
| 분석 run | step 7개가 1.2초씩 진행. 완료 전 `/result`는 409 `not_ready` |
| SSE `/events` | step 전이를 그대로 흘려보내고 `completed` 후 스트림 종료 |
| 후보 page | `page=2` 이상은 최초 202 `analyzing`, 2.5초 뒤 재요청하면 200 |
| 면접 준비 | 생성 후 3.5초는 `preparing`, 이후 `in_progress` + 1턴 |
| 리포트 | 최초 조회에서 생성 시작, 3초 뒤 재요청하면 200 |

새로고침하면 저장소가 초기화된다. 분석부터 다시 하지 않도록 seed 레코드가 있다.

| seed | 값 |
| --- | --- |
| 완료된 run | `5c7b9e10-0000-4000-8000-00000000aaaa` |
| 종료된 면접 | `a3d51c20-1001-4c00-9a00-000000000001` |

## 7. 핸들러 추가할 때

- 경로는 `path('/...')`로 쓴다. `shared/api.ts`의 `BASE`를 따라간다.
- 응답은 `HttpResponse.json<타입>()`으로 타입을 고정한다. 계약이 바뀌면 컴파일 단계에서 깨져야 한다.
- 에러는 `errorResponse(status, reason, message)`로 만들고, `reason`은 `backend/docs/error-reasons.md`에 있는 값만 쓴다.
- 핸들러가 없는 `/api` 경로는 catch-all이 501과 콘솔 에러로 알려준다. 501이 보이면 핸들러 누락이다.

## 완료 조건

- [x] 개발 서버에서 워커가 시작되고 `/api/*`를 가로챈다
- [x] `openapi.yaml`의 Sprint 1 엔드포인트 정상 흐름을 모두 응답한다
- [x] 분석 run·면접 준비·리포트·후보 page의 상태 전이가 동작한다
- [x] SSE가 step 이벤트를 흘려보내고 `completed`로 끝난다
- [x] 미등록 `/api` 경로가 조용히 통과하지 않는다
- [x] 프로덕션 빌드에 mock이 포함되지 않는다
- [x] `npm run lint`, `npm run build` 통과

검증 결과는 설계 문서의 검증 표에 기록했다. lint/build는 동작 테스트가 아니다.

## 다음 작업

실패 케이스 핸들러, WebSocket mock 방식 결정.

## 커밋

```
feat: add msw mock api handlers
```
