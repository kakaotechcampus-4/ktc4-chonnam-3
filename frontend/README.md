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

기본 실행은 `/api` 프록시로 실제 백엔드에 연결한다. 화면 미리보기용 MSW mock API는 개발 환경에서 `.env.local`에 `VITE_USE_MSW=true`를 설정했을 때만 켜진다. 실제 GitHub 로그인 검증은 이 값을 제거하거나 `false`로 설정한 뒤 진행한다. 자세한 내용은 [`docs/task-07-msw.md`](docs/task-07-msw.md) 참고.

mock은 고정된 로그인 사용자 정보를 반환하므로 로그아웃 후에도 홈으로 돌아온다. 실제 로그인·로그아웃 검증에는 mock을 사용하지 않는다.

API 요청은 `src/shared/api.ts`에서 `/api` prefix로 호출. 응답/요청 타입은 `src/types/api.ts`, API 스펙은 [`docs/api-spec.md`](../docs/api-spec.md) 참고.

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- `main`은 최종 배포용 (develop → main PR에서만 컨벤션 봇 안내 발생).
- 브랜치명 예: `feature/fe-xxx`, `fix/fe-xxx`.
