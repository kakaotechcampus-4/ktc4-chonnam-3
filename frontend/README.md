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
├─ types/         # API 타입
├─ routes.tsx     # 라우트 정의
├─ providers.tsx  # 전역 Provider (QueryClient 등)
└─ main.tsx       # 엔트리 포인트
```

API 요청은 `src/shared/api.ts`에서 `/api` prefix로 호출. 응답/요청 타입은 `src/types/api.ts`, API 스펙은 [`docs/api-spec.md`](../docs/api-spec.md) 참고.

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- `main`은 최종 배포용 (develop → main PR에서만 컨벤션 봇 안내 발생).
- 브랜치명 예: `feature/fe-xxx`, `fix/fe-xxx`.
