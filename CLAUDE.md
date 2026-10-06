# DEVON 코딩 AI 작업 지침

이 파일은 코딩 AI의 작업 방법과 문서 라우팅만 정의한다.
서비스 요구사항·용어·API·아키텍처·완료 조건의 원본은 spec/이다. 명세 내용을 이 파일에 복제하지 않는다.
사용자의 현재 지시와 승인 범위를 우선한다.

## 라우팅 — 경로는 저장소 루트 기준
| 작업 | 읽을 지침 | 읽을 명세 |
| --- | --- | --- |
| FE | frontend/CLAUDE.md | spec/frontend/architecture.md, 관련 features 문서 |
| BE | backend/CLAUDE.md | spec/backend/architecture.md, 관련 features 문서 |
| AI 기능 | ai/CLAUDE.md; backend 코드 수정 시 backend/CLAUDE.md도 확인 | spec/ai/architecture.md, 관련 features 문서 |
| API·이벤트·공유 타입 | 관련 팀 CLAUDE.md | spec/shared/contracts/README.md, migration.md, 관련 스키마 |
| 공통 용어·결정 | 관련 팀 CLAUDE.md | spec/shared/glossary.md, spec/shared/decisions/README.md |
| PR 준비 | /overlap-check, /contract-check, /pr-ready | 변경한 기능의 verification 문서 |
| 작업 인계 | /handoff | 필요할 때만 관련 명세 참조 |

## 생성 위치
- 서비스 기능 명세: spec/<팀>/features/<기능>.md.
- 아키텍처: spec/<팀>/architecture.md. 설계 초안과 현재 구현을 구분한다.
- 검토할 설계 산출물: spec/<팀>/designs/YYYY-MM-DD-<주제>.md. Proposed/Accepted 상태 명시.
- 공통 계약·용어 결정: spec/shared/decisions/. 내부 구현 결정: spec/<팀>/decisions/.
- AI의 실행 순서·파일 편집 계획: .claude/scratch/plans/. 개인 인계·추론 메모: .claude/scratch/.
- 임시 실행 로그: <팀>/report/. 팀에 공유할 요구사항·결정·검증 근거는 spec/ 또는 PR에 남긴다.
- 실행 계획에 합의해야 할 설계가 생기면 관련 spec 문서에 제안한다. 임시 계획을 명세 원본으로 취급하지 않는다.
- 기존 frontend/docs·backend/docs의 원본 유지·API 이관 범위는 spec/README.md의 안내를 따른다. 내용을 복제하거나 기존 파일을 자동 삭제하지 않는다.

## 문서 기록 원칙
- 초기 설계 문서는 설계 기준선으로 보존한다. 구현에 맞춰 계속 덮어쓰거나 구현 완료·미완료·테스트 결과를 덧붙이지 않는다. Proposed/Accepted는 설계의 승인 상태이며 구현 상태가 아니다.
- 구현·수정 내역, 코드 위치, 검증 결과와 남은 작업은 별도 구현 기록 한 곳에서 관리한다. AI 작업의 원본은 `spec/ai/implementation.md`로 통일하며, 다른 문서는 같은 현황을 복제하지 않고 해당 기록을 참조한다.
- `testing.md`에는 검증 방법·환경·기준을, task 문서에는 목표·선행 조건·완료 조건을 둔다. 실제 실행 결과와 진행 현황은 구현 기록에 모은다.
- 중요한 설계·정책 변경은 `decisions/`에 맥락·결정·이유·영향·관련 PR과 이전 결정의 대체 관계를 남긴다. 기존 설계·결정을 현재 구현에 맞춰 덮어쓰지 않고 후속 ADR과 필요시 새 설계 문서로 변경을 추적한다.
- 현행 API·내부 계약 정의는 실제 계약 변경에 맞춰 갱신하되 구현 일지를 섞지 않는다. PR에는 변경과 검증을 요약하고 구현 기록·ADR을 연결한다.

## 변경·검증
- 명세를 바꿀 때 spec에서 먼저 영향·상태를 확인하고 관련 구현·테스트·소비 팀을 함께 검토한다.
- 공통 API의 원본·예외 범위는 spec/shared/contracts/README.md를 따른다. spec/shared/contracts/migration.md에 남은 개별 충돌·보류를 임의로 합의 처리하지 않는다.
- 수정한 팀 지침의 실제 검증 명령을 실행하고 통과·실패·미실행·범위 밖을 구분한다.
- 계약 검사: 루트에서 python3 .claude/scripts/check_contracts.py. 부분 형식 검사만으로 전체 서비스 검증을 주장하지 않는다.
- 스켈레톤·README의 실행 예시는 실행 성공의 증거가 아니다.
- 운영진 CODEOWNERS 네 줄과 assign-mentor/notify-discord/convention-check 워크플로를 보존한다.
- 커밋·푸시·PR 생성은 현재 사용자가 요청한 범위에 포함될 때만 수행한다.

## Superpowers 연결
설계 검토·계획·구현·테스트·리뷰에 사용하되 위 저장 위치를 적용한다.
팀이 검수할 설계 문서는 spec/, 세션 실행 계획은 .claude/scratch/plans/에 둔다.
플러그인 설치·활성화는 개발 환경에서 별도 확인한다. 이 파일만으로 설치되지 않는다.
서브에이전트를 사용할 때도 관련 팀 지침과 명세 경로를 전달한다.
