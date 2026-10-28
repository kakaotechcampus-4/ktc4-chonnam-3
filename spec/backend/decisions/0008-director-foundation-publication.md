# 0008 Director 연결에 필요한 BE 공통 보완의 게시 경계

- 상태: Proposed
- 날짜: 2026-10-23
- 범위 정리: 2026-10-25, PR #127
- 선행 PR: migration #82·#108
- 설명 정리: 2026-10-28, 결정·이유·보호 조건은 유지하고 실행 경위의 중복을 줄인다.

## 맥락

최초 게시 당시 공고 버전과 Agent 저장 migration은 별도 head였다. 이후 선행 PR마다
합류 지점이 추가되어, 공개한 revision의 이력을 보존하면서 최종 head를 합쳐야 한다.
검사 subprocess가 다른 worktree의 editable 설치를 읽는 문제와 seed 수정 범위도 구분한다.

## 결정과 이유

- 공유·배포 DB의 전체 적용 이력을 확인할 수 없으므로 기존 revision ID·부모·DDL을 재작성하지 않는다.
- `0003_director_runtime`은 `0003_agent_storage_merge`와 부모가 같지만 기존 경로의 이력을 보존한다.
  부모에서만 제외하면 별도 head가 남고, 파일까지 제거하면 그 revision을 가리키는 DB의 해석을 깨뜨릴 수 있다.
  최초 docstring은 작성 당시의 head 연결 맥락이며 현재 유지 이유는 이력 보존이다.
- 검사 subprocess는 해당 worktree의 BE·AI 소스를 명시해 다른 editable 설치를 읽지 않는다.
- 선행 migration은 복사하지 않으며 필요한 선행을 실제 반영한 graph와 PostgreSQL에서 검증한다.
- seed 실행 코드와 관련 추가 테스트는 #127에서 제외하고 원본 이력에 보존한다.
  #131의 구현을 복사하거나 그 해결을 #127의 완료 범위로 보고하지 않는다.

## 영향

공개 API·DB 테이블 정의·운영 prompt 활성화 정책은 바꾸지 않는다. Director 코어·연결 기반·명세는
별도 PR이며 준비 실행·WS 등록은 포함하지 않는다. 이 문서는 기존 Task 9의 0002와 구분해 0008로 식별한다.
실제 실행 결과·실패·검증 한계의 원본은 [AI 구현 기록](../../ai/implementation.md)이다.
루트 CLAUDE 문서 기록 원칙과 AI ADR 0020에 따라 BE 문서에 같은 현황을 복제하지 않는다.

## 2026-10-26 리뷰에 따른 후속 연결

기존 `0003_director_runtime`만으로 #82·#108까지 합칠 수 없어 DDL 없는
`0004_interview_foundation_merge`를 추가한다. 부모는 `0003_agent_storage_merge`,
`0003_director_runtime`, `0003_analysis_runs`이며 이전 경로는 보존한다.
선행 부재 시에는 develop base의 Draft로 검토한다. 당시 seed 수집 오류의 후속 해결은 #131의 범위다.

## 2026-10-27 순차 게시 단계의 추가 합류

최종 결합뿐 아니라 #108 반영 직후에도 단일 head를 유지하도록 합류 지점을 보완한다.
당시 중간 검증 누락과 실제 재검사 결과는 AI 구현 기록에 남긴다.

- #108의 `0004_analysis_storage_merge`는 `0003_agent_storage_merge`·`0003_analysis_runs`를 합친다.
- #127의 최종 `0005_director_foundation_merge`는 위 합류와 `0004_interview_foundation_merge`를 합친다.
- 실제 revision metadata로 develop·#82·#108·#127의 네 snapshot을 검사한다.

## 되돌리기와 병합 조건

- 여러 부모가 있는 합류 지점에서는 모호한 `downgrade -1` 대신 대상 revision을 명시한다.
- merge만 되돌리는 경로와 분석 DDL까지 되돌리는 경로를 구분한다. 중복 active 분석 작업이 있으면
  `0002_posting_versions`로의 downgrade를 기존 #108 guard가 막고 자료·version 집합을 보존해야 한다.
- merge-only 왕복은 위 위험 downgrade 검증을 대신하지 않는다.
- 현재 develop에 필요한 선행이 반영되고 실제 graph·자료 보존·필수 CI를 확인한 뒤 Draft 해제를 판단한다.
  최신 병합 상태와 실제 실행 결과는 AI 구현 기록과 PR 본문에서 확인한다.
