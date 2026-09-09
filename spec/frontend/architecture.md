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
