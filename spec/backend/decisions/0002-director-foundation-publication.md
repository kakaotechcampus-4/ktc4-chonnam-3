# 0002 Director 연결에 필요한 BE 공통 보완의 게시 경계

- 상태: Proposed
- 날짜: 2026-10-23
- 범위 정리: 2026-10-25, PR #127
- 선행 PR: migration #82

## 맥락

공고 버전과 agent 저장 migration은 별도 head이며, 검사 subprocess가 다른 worktree의
editable 설치를 읽으면 이번 소스의 검증 결과를 보장할 수 없다.
seed CLI의 폐기된 session factory 참조는 #131의 별도 수정 범위다.

## 결정과 이유

- seed 실행 코드와 관련 추가 테스트는 #127에서 제외하고 원본 이력에 보존한다.
  #131을 병합하거나 해당 구현을 이 PR에 복사하지 않는다.
- `0003_director_runtime`은 DDL 없이 두 head만 연결하고 원래 migration을 바꾸지 않는다.
- 검사 subprocess는 해당 worktree의 BE·AI 소스를 명시해 다른 editable 설치를 읽지 않는다.
- 선행 migration을 이 PR에 복사하지 않는다. #82 없이는 migration graph 검증이 실패하므로
  해당 의존을 해소하고 실제 PostgreSQL에서 재검증하기 전 병합하지 않는다.

## 영향

공개 API·DB 테이블 정의·운영 prompt 활성화 정책은 바꾸지 않는다.
Director 코어·연결 기반·명세는 별도 PR이며 준비 실행·WS 등록은 포함하지 않는다.
seed 오류 해결은 #131의 반영으로 확인하며, 이 PR의 완료 범위로 보고하지 않는다.
결과는 [AI 구현 기록](../../ai/implementation.md)의 게시 검증 기록을 따른다.
