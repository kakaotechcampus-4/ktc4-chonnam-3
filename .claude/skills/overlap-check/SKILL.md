---
name: overlap-check
description: 작업 시작 또는 PR 준비 시 변경 예정 파일과 확인 가능한 다른 작업의 중복·공통 계약 영향을 점검한다.
---

# overlap-check

루트 CLAUDE.md, spec/<팀>/architecture.md, spec/shared/contracts/migration.md를 확인한다.
1. 현재 브랜치, git status --short, staged·unstaged 변경과 기준 브랜치 대비 커밋 차이를 확인한다. untracked 파일도 포함한다.
2. 기준 브랜치는 사용자 지정 우선, 없으면 PR base 또는 로컬 origin/develop. ref가 없으면 확인 불가로 보고한다. 작업 트리를 변경하지 않는다.
3. GitHub 읽기 도구 또는 gh가 인증되어 있으면 같은 base의 열린 PR 파일 목록을 확인한다. 권한·도구가 없으면 원격 중복은 미검증으로 표시한다.
4. 파일 경로가 다르더라도 같은 endpoint·schema·enum·AI/BE 경계를 수정하는지 검토한다.
5. 결과 표: 파일/계약, 내 변경, 겹치는 PR, 영향 팀, 필요한 조정. 팀원 로컬 작업까지 확인했다고 주장하지 않는다.
읽기·보고만 수행한다. 작업 예약·담당자 지정·댓글·fetch/push를 자동으로 수행하지 않는다.
