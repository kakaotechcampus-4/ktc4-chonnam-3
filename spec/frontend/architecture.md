# FE 아키텍처 — 현재 기반

기준: 2026-09-09 develop의 README·디렉터리. 폴더 존재가 기능 완성을 뜻하지 않는다.

| 경로 | 책임 |
| --- | --- |
| frontend/src/features/ | 도메인별 화면·로직 |
| frontend/src/shared/api.ts | 공통 HTTP 요청·에러 처리 |
| frontend/src/types/api.ts | API 요청·응답 타입 |
| frontend/src/routes.tsx, providers.tsx | 라우팅·전역 Provider |

현재 기술 기반: React·TypeScript·Vite. 상세 실행법은 frontend/README.md.
API 명세 이관 상태는 spec/shared/contracts/migration.md에 기록한다.

## 폴더 구조 / 배치 기준

frontend/md/hierarchy.md에서 이관.

```
src/
├─ features/      # 도메인별 화면·로직 (auth, home, interview, analysis, report, mypage)
│  └─ <feature>/
│     ├─ *.tsx      # 해당 기능 전용 컴포넌트/페이지
│     └─ hooks/      # 해당 기능 전용 훅 (다른 feature에서 안 씀)
├─ shared/        # 2개 이상 feature에서 공용으로 쓰는 것
│  ├─ api.ts        # API 클라이언트 wrapper
│  ├─ queryKeys.ts  # TanStack Query 키 팩토리
│  └─ components/   # 공용 UI 컴포넌트 (AppHeader 등)
├─ types/         # API 요청/응답 타입 (docs/api-spec.md 기준)
├─ routes.tsx     # 라우트 정의
├─ providers.tsx  # 전역 Provider (QueryClient 등)
└─ main.tsx       # 엔트리 포인트
```

- **feature 전용 vs shared 판단**: 지금 한 곳에서만 쓰면 `features/<feature>/` 안에 둔다. 두 번째 feature가 같은 걸 필요로 하는 시점에 `shared/`로 옮긴다 (미리 옮기지 않음).
- **컴포넌트 vs 훅 분리**: JSX 없는 로직(fetch 조합, 폼 상태 등)은 `hooks/`, 나머지는 컴포넌트 파일에 같이 둔다.
- 새 feature 폴더 추가 시 `routes.tsx`에 라우트 등록 + `spec/frontend/features/<기능>.md` 신규 작성.

## 라우트 (`context/FE.md`에서 이관, `frontend/src/routes.tsx` 기준 확정)

| # | 화면 | 경로 | 컴포넌트 파일 |
| --- | --- | --- | --- |
| 1 | 로그인 | `/login` | `features/auth/Login.tsx` |
| — | 홈 | `/home` | `features/home/Home.tsx` |
| — | 마이페이지 | `/mypage` | `features/mypage/MyPage.tsx` |
| 4-v2 | 공고 입력 | `/interview/new` | `features/analysis/JobInput.tsx` |
| 4-2-v2 | 분석 진행 | `/interview/analyzing/:runId` | `features/analysis/Analyzing.tsx` |
| 4-3-v2 | 분석 실패 | `/interview/failed/:runId` | `features/analysis/AnalysisFailed.tsx` |
| 5a-v2 | 레포 확정 | `/interview/repos/:runId` | `features/analysis/RepoSelect.tsx` |
| 5a2-v2 | 면접 준비 (1b 포함) | `/interview/:id/prepare` | `features/interview/InterviewPrepare.tsx` |
| 5b-v2 | 면접 진행 | `/interview/:id/session` | `features/interview/InterviewScreen.tsx` |
| 5c-v2 | 리포트 | `/interview/:id/report` | `features/report/Report.tsx` |
| — | 미정의 경로 | `*` | `/home` 리다이렉트 |

**`:runId` vs `:id` 경계**: 분석 단계(`/interview/new` ~ `/interview/repos/:runId`)는 `runId`, 면접 단계(`/interview/:id/prepare` ~ `/interview/:id/report`)는 `id`(`interviewId`)를 쓴다. `POST /interviews`가 두 단계의 경계다.

경로에 ID를 박아두는 이유:

- **새로고침 복구**: `/interview/analyzing`만 있으면 F5 시 어느 분석인지 모른다. `/interview/analyzing/run_abc123`이어야 `GET /analysis-runs/{runId}`로 상태를 되살릴 수 있다. 5a2-v2·5b-v2도 마찬가지로 `GET /interviews/{id}`로 복구한다.
- **과거 리포트 조회**: 마이페이지에서 면접 클릭 → `/interview/{id}/report`로 바로 이동해야 한다.
- **링크 공유**: URL이 상태를 담아야 특정 리포트 주소를 그대로 공유할 수 있다.

**라우트 순서 주의**: `/interview/new`가 `/interview/:id/prepare`보다 먼저 와야 한다(React Router v6는 구체적 경로를 우선 매칭하지만 명시적으로 순서를 지킨다). 새 라우트 추가 시 이 순서를 유지한다.

## `/api` 프리픽스

화면 경로(React Router)와 API 경로(BE)는 완전히 별개다. CloudFront rewrite로 갈린다(`context/FE.md`):

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<BE>/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

`/api`로 시작하지 않는 요청은 전부 화면 경로(SPA)로 취급된다. 그래서 BE로 가는 모든 요청은 실제로 `/api`가 붙어야 한다.

- **`fetch` 기반 호출**: `shared/api.ts`의 `const BASE = '/api'`가 자동으로 붙여준다. `spec/frontend/features/*.md`·`frontend/docs/api-spec.md`의 엔드포인트 문서는 이 프리픽스를 뺀 논리 경로로 적는다(래퍼가 처리하므로).
- **`EventSource`·`WebSocket`**: 이 래퍼를 거치지 않는다. **URL에 `/api`를 직접 포함해야 한다** — `new EventSource('/api/analysis-runs/...')`, `GET /api/ws/interviews/...`. 이 두 곳만 예시 코드에 `/api`를 실제로 써둔다.

**미확인**: CloudFront가 WebSocket Upgrade 핸드셰이크와 SSE 스트림에도 이 경로 rewrite를 문제없이 통과시키는지는 배포 설정에서 실제 확인이 필요하다(일반 HTTP rewrite와 별개로 WS는 프록시가 Upgrade 헤더를 명시적으로 지원해야 하는 경우가 많다).
