---
name: contract-check
description: API·공유 스키마·enum·이벤트 변경 또는 PR 준비 시 계약 형식과 소비 코드 영향을 확인한다.
---

# contract-check

spec/shared/contracts/README.md와 migration.md를 먼저 읽는다.
1. 프로젝트 루트에서 python3 .claude/scripts/check_contracts.py를 실행한다. 의존성이 없으면 requirements-checks.txt를 안내하고 미실행으로 표시한다.
2. 기준 브랜치 대비 spec/shared/contracts, frontend/src/types/api.ts, frontend/docs/api-spec.md, backend/docs/api-spec.md 및 관련 구현 diff를 비교한다. ref 미확인은 보고한다.
3. required/optional, null, enum, 상태코드, 에러 봉투, SSE/WS, 호환성·이관 순서를 검토한다. 기존 migration의 불일치를 통과로 바꾸지 않는다.
4. 실제 존재하는 backend/tests/contract 테스트와 관련 변경 테스트를 실행한다. 없으면 테스트 부재로 보고한다.
5. 결과를 형식 검증 / 구현 일치 / 호환성 / 미확정 결정으로 구분하고 영향 팀과 필요한 파일을 적는다.
부분 스키마 검사 성공을 전체 API 또는 배포 준비 완료로 표현하지 않는다. 계약 내용은 요청에 수정 권한이 있을 때만 바꾼다.
