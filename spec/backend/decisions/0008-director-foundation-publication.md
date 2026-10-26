# 0008 Director 연결에 필요한 BE 공통 보완의 게시 경계

- 상태: Proposed
- 날짜: 2026-10-23
- 범위 정리: 2026-10-25, PR #127
- 선행 PR: migration #82·#108

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

## 2026-10-26 리뷰에 따른 후속 연결

위 결정은 당시 두 head의 연결 이력으로 보존한다. #82가 추가하는
`0003_agent_storage_merge`와 #108의 `0003_analysis_runs`까지 포함하면 기존
`0003_director_runtime`만으로 최종 head를 하나로 만들 수 없다.

- 공유·배포 DB 적용 이력을 확인할 수 없으므로 기존 revision ID·부모·DDL을 재작성하지 않는다.
- DDL 없는 `0004_interview_foundation_merge`를 추가해 위 두 후속 revision과
  기존 `0003_director_runtime`을 합친다. 단일 head와 기존 자료 보존을 검증한다.
- #82는 자체 신규 merge로 develop의 공고 버전 이력과 연결한다. #127은 #82·#108
  반영 전에는 graph를 해석할 수 없으므로 develop을 base로 유지하고 Draft로 검토한다.
- 과거 #131 seed 수집 오류는 이후 develop에서 해결된 상태다. seed 구현은 #127에 복사하지 않는다.
- 검사 subprocess의 worktree 소스 경로 보완은 유지한다. 순수 BE 코드 경로라는 이유로
  Director 분리 게시·통합 검증의 원본을 중복 기록하지 않는다. 이 작업의 원본은 AI 구현 기록이며
  BE 문서는 그 기록을 참조한다(루트 CLAUDE 문서 기록 원칙·AI ADR 0020).

기존 `0002-task09-persistence.md`와 번호를 구분하기 위해 이 문서는 0008로 식별한다.
이 변경은 제품 API·질문 정책·테이블 정의를 바꾸지 않는다.

합류 revision의 되돌리기는 대상 revision을 명시한다. 여러 부모가 있는 지점의
`downgrade -1`은 경로가 모호하므로 실행할 이전 revision과 그 자료 보존 조건을 먼저 확인한다.

## 2026-10-27 순차 게시 단계의 추가 합류

위 최종 합류만으로는 develop → #82 → #108 단계의 단일 head를 보장하지 못했다.
당시 검증은 #127까지 모두 결합한 graph를 확인했고, #108 반영 직후의 두 head를 놓쳤다.
이전 revision과 실행 기록은 그대로 보존하고 현재 합류 지점을 다음과 같이 보완한다.

- #108은 DDL 없는 `0004_analysis_storage_merge`에서 `0003_agent_storage_merge`와
  `0003_analysis_runs`를 연결한다. #108까지 반영한 시점도 단일 head여야 한다.
- #127은 DDL 없는 `0005_director_foundation_merge`를 추가한다. 부모는 위 #108의
  신규 합류와 기존 `0004_interview_foundation_merge`이며, 기존 ID·부모·DDL은 유지한다.
- 현재 목표 head는 `0005_director_foundation_merge`다. 이전 절의 0004는 보존할 이력이고
  최종 목표에 관한 설명은 이 절을 따른다. 제품 계약·테이블·자료 정책은 바꾸지 않는다.
- 실제 revision metadata로 develop·#82·#108·#127의 네 snapshot을 각각 검사한다.
  선행이 없는 게시본의 실패는 유지하며, 새 #108 합류까지 반영한 뒤 병합 전에 재검증한다.
- merge만 되돌리는 대상과 분석 DDL까지 되돌리는 대상은 구분한다. 활성 분석 작업이 중복된
  상태에서 `0002_posting_versions`로 내려가면 기존 #108 차단이 실행되고 자료·version 집합을
  보존해야 한다. merge-only 왕복이 이 위험 downgrade 검증을 대신하지 않는다.

새 실행 결과와 검사 한계의 원본은 [AI 구현 기록](../../ai/implementation.md)에 추가한다.
