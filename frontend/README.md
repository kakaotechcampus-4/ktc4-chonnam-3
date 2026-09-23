# Frontend

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 (전남대 3팀) FE.

## 기술 스택

- React 19 + TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query

## 시작하기

```bash
git clone <repo-url>
cd ktc4-chonnam-3/frontend
npm install
npm run dev
```

`http://localhost:5173` 접속.

## 스크립트

| 명령어 | 설명 |
| --- | --- |
| `npm run dev` | 개발 서버 실행 |
| `npm run build` | 타입 체크 + 프로덕션 빌드 |
| `npm run preview` | 빌드 결과 로컬 미리보기 |
| `npm run lint` | ESLint 검사 |
| `npm test` | MSW 기반 인증 화면 Playwright 테스트 (Chromium 필요) |
| `npm run test:integration` | 실제 API·Vite·DB·Redis 인증 통합 테스트 (아래 격리 환경 필요) |
| `npm run format` | Prettier 포맷팅 |

## 폴더 구조

```
src/
├─ features/      # 도메인별 화면·로직 (auth, home, interview, analysis, report, mypage)
├─ shared/        # API 클라이언트(api.ts), React Query 키(queryKeys.ts)
├─ mocks/         # MSW mock API (개발 서버 전용)
├─ types/         # API 타입
├─ routes.tsx     # 라우트 정의
├─ providers.tsx  # 전역 Provider (QueryClient 등)
└─ main.tsx       # 엔트리 포인트
```

개발 서버에서는 MSW mock API가 기본으로 켜진다. 끄려면 `.env.local`에 `VITE_USE_MSW=false`를 넣는다. 자세한 내용은 [`docs/task-07-msw.md`](docs/task-07-msw.md) 참고.

실제 인증 연동에서는 백엔드를 `localhost:8000`에서 실행한다. Vite는 `/api`를 그대로 전달하고, 공개 OAuth 콜백 `/auth/github/callback`은 `/api/auth/github/callback`으로 전달한다. GitHub OAuth App과 서버의 callback 설정은 `http://localhost:5173/auth/github/callback`으로 맞춘다. 개발 포트가 사용 중이면 다른 포트로 자동 전환하지 않는다.

화면 개발용 mock 세션은 기본 로그인 상태다. 로그아웃 뒤에는 새로고침해도 인증 요청이 거절된다. 다시 화면을 개발하려면 콘솔에서 `msw.clear(); msw.session('authenticated')` 실행 후 `/home`을 새로 연다. 이 기능은 GitHub OAuth·HttpOnly 쿠키를 흉내 내지 않는다.

인증 화면 테스트는 `npm ci`, `npx playwright install chromium`, `npm test`로 실행한다. 테스트 서버는 `localhost:5174`, 결과는 저장소의 `.claude/scratch/oauth-session-frontend/results`를 사용한다.

실제 세션 통합 테스트는 GitHub의 동의 화면·토큰·사용자 응답만 대체하고 Vite, FastAPI, PostgreSQL, Redis와 브라우저 쿠키를 사용한다. `backend`의 의존성을 먼저 설치하고 Python 3.12 가상환경과 Node를 PATH에 둔다. **폐기 가능한 별도 PostgreSQL DB와 Redis 인스턴스**를 준비한다. 테스트 서버는 시작할 때 아래 DB의 사용자 데이터를 비우고 Redis DB 13을 `FLUSHDB`하므로 실제 서비스 주소를 사용하면 안 된다.

```bash
# 실제 주소는 별도 테스트 인스턴스에 맞춘다. DB 이름의 끝은 _oauth_browser_test여야 한다.
export TEST_DATABASE_URL=postgresql+asyncpg://devon@127.0.0.1:55433/devon_oauth_browser_test
export TEST_REDIS_URL=redis://127.0.0.1:56380/13
npm run test:integration
```

PowerShell에서는 `export NAME=value` 대신 `$env:NAME='value'`를 사용한다. 5173과 8000 포트가 비어 있어야 하며 테스트가 전용 API·Vite 서버를 시작하고 종료한다. 로그인·재연동 모두 `/auth/github/callback` 하나를 사용하며, PKCE, HttpOnly 쿠키, 새로고침, 콜백 재사용 거절, 로그아웃을 확인한다. 산출물은 `.claude/scratch/oauth-session-browser/results`에 저장한다. 이 테스트는 실제 GitHub 계정의 동의나 운영 배포를 검증하지 않는다.

API 요청은 `src/shared/api.ts`에서 `/api` prefix로 호출한다. 일반 HTTP API의 원본은 [OpenAPI](../spec/shared/contracts/openapi.yaml)이며, WebSocket·SSE·브라우저 이동 경로는 [`docs/api-spec.md`](docs/api-spec.md)를 따른다. 원본의 적용 범위와 미합의 항목은 [공통 계약 안내](../spec/shared/contracts/README.md)와 [이관 현황](../spec/shared/contracts/migration.md), FE용 타입은 `src/types/api.ts`에서 확인한다.

문서의 요구사항과 로컬 구현 상태는 구분한다. 면접 준비·진행 화면은 현재 골격이며 보류된 화면 보완은 `docs/task-*.md`의 후속 작업이다. lint/build와 MSW 기반 화면 테스트는 실제 GitHub·Redis·배포 환경 검증을 대신하지 않는다.

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- `main`은 최종 배포용 (develop → main PR에서만 컨벤션 봇 안내 발생).
- 브랜치명 예: `feature/fe-xxx`, `fix/fe-xxx`.
