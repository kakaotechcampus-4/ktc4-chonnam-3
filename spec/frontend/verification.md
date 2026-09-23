# FE 검수·완료 기준

| 검수 항목 | 상태 | 근거 |
| --- | --- | --- |
| 기능 명세의 정상·실패 동작 충족 | 미검증 | spec/frontend/features/*.md의 "검증 시나리오" |
| API·공유 타입·이벤트 계약과 일치 | 미검증 | spec/shared/contracts/, frontend/src/types/api.ts |
| 현재 구조와 설계 문서의 차이 명시 | 미검증 | spec/frontend/architecture.md |
| 관련 테스트·빌드 결과 기록 | 미검증 | frontend/docs/task-*.md의 "완료 조건" |
| 공통 통합 시나리오 충족 | 미검증 | spec/shared/checklist.md |
| 미구현·미합의·후속 작업 명시 | 미검증 | 각 feature 문서의 `PENDING_TEAM`/`PENDING_FE` 표기, frontend/docs/task-*.md |

기능별 상세 검증 시나리오는 spec/frontend/features/<기능>.md에, 구현 완료 체크리스트는 frontend/docs/task-*.md에 둔다. 이 문서는 팀 전체가 보는 공통 검수 기준만 유지한다.

`frontend/package.json`의 `npm test`는 MSW 기반 인증 화면 테스트이며, `npm run test:integration`은 GitHub HTTP만 대체하고 Vite·API·PostgreSQL·Redis·브라우저 쿠키를 연결하는 별도 테스트다. 실행 조건과 결과는 `frontend/README.md`와 `frontend/docs/task-07-auth.md`를 따른다. 브라우저용 `frontend/docs/msw-smoke-check.js`는 수동 실행 스크립트이며 OpenAPI 전체·실제 GitHub 인증·WS·운영 배포 동작을 자동 검증하지 않는다. 설계 문서에 보존된 과거 통과 기록과 현재 실행 결과를 구분한다. 면접 준비·진행 화면의 로컬 골격과 task 문서의 미완료·수정 보류 항목도 구현 완료로 세지 않는다.

이 표는 팀이 결과를 검수하는 기준이다. AI의 실행 명령·PR 준비 순서는 CLAUDE.md와 .claude/skills/에서 관리한다.
