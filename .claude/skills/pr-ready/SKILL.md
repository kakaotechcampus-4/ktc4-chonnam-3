---
name: pr-ready
description: 현재 변경을 PR로 검수하기 전에 팀별 검증·공통 계약·문서·결정 기록을 점검하고 PR 본문 초안을 작성한다.
---

# pr-ready

루트 및 변경 영역의 CLAUDE.md, .github/pull_request_template.md를 읽는다.
1. staged/unstaged/untracked 및 base 대비 커밋 변경을 확인하여 이번 작업과 기존 사용자 변경을 구분한다.
2. /overlap-check, /contract-check가 수행된 경우 같은 변경에 대한 결과를 재사용한다. 이후 수정되어 근거가 낡았으면 관련 부분만 다시 검증한다.
3. 변경한 팀의 검증 명령을 실제 실행. 현재 FE test 스크립트 부재, BE 스켈레톤 등은 미실행·제약으로 기록한다.
4. spec의 기능 명세·verification·공통 또는 내부 ADR 필요 여부와 운영진 보호 파일 변경을 확인한다.
5. PR 템플릿에 결정/이유/영향, 실행 디렉터리·명령·결과, 리뷰 질문, 미완료를 채워 초안을 제시한다.
실패나 확인 불가가 있으면 준비 완료 대신 남은 항목을 표시한다. 명시된 사용자 요청 없이 commit/push/PR 생성·리뷰 요청을 수행하지 않는다.
