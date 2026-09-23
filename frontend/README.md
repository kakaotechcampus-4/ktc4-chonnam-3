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

API 요청은 `src/shared/api.ts`에서 `/api` prefix로 호출한다. 일반 HTTP API의 원본은 [OpenAPI](../spec/shared/contracts/openapi.yaml)이며, WebSocket·SSE·브라우저 이동 경로는 [`docs/api-spec.md`](docs/api-spec.md)를 따른다. 원본의 적용 범위와 미합의 항목은 [공통 계약 안내](../spec/shared/contracts/README.md)와 [이관 현황](../spec/shared/contracts/migration.md), FE용 타입은 `src/types/api.ts`에서 확인한다.

문서의 요구사항과 로컬 구현 상태는 구분한다. 면접 준비·진행 화면은 현재 골격이며, 인증 연결과 보류된 화면 보완은 `docs/task-*.md`의 후속 작업이다. `npm run test` 스크립트는 없고 lint/build 통과만으로 화면·실서버 동작이 검증되지는 않는다.

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- `main`은 최종 배포용 (develop → main PR에서만 컨벤션 봇 안내 발생).
- 브랜치명 예: `feature/fe-xxx`, `fix/fe-xxx`.
