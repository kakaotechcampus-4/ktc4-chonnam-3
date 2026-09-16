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
- 기존 frontend/docs·backend/docs는 아직 이관 전이다. spec/README.md의 원본 링크를 따른다. 내용을 복제하거나 기존 파일을 자동 삭제하지 않는다.

## 변경·검증
- 명세를 바꿀 때 spec에서 먼저 영향·상태를 확인하고 관련 구현·테스트·소비 팀을 함께 검토한다.
- 공통 계약은 전환 초안이다. spec/shared/contracts/migration.md의 충돌을 임의로 합의 처리하지 않는다.
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
