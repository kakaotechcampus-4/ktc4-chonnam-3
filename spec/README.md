# DEVON 서비스 명세

## 문서 경계
이 디렉터리는 팀원이 합의하고 검수하는 서비스 요구사항·설계·계약·검증 기준의 원본이다.
사람과 코딩 AI가 같은 spec 문서를 참조한다. AI 전용으로 명세를 복사하지 않는다.

| 내용 | 위치 |
| --- | --- |
| 공통 용어·통합 검수 기준·공통 결정 | spec/shared/ |
| OpenAPI·JSON Schema·계약 이관 상태 | spec/shared/contracts/ |
| FE·BE·AI 기능 요구사항 | spec/<팀>/features/ |
| 아키텍처·검수할 설계 | spec/<팀>/architecture.md, designs/ |
| 검증 기준·내부 구현 결정 | spec/<팀>/verification.md, decisions/ |
| 코딩 AI가 읽을 문서·명령·작업 방법 | 루트·팀 CLAUDE.md, .claude/skills/ |
| 코딩 AI의 임시 실행 계획·인계 | .claude/scratch/ — Git 추적 제외 |

spec/ai는 서비스 AI 기능의 명세다. 코딩 AI용 규칙 폴더가 아니다.
설계 초안은 Proposed, 승인된 설계는 Accepted로 구분한다. 세션별 편집 순서·추론 메모는 spec에 넣지 않는다.

## 기존 문서와의 전환
이번 수정은 이전 검수 초안의 배치를 변경한다. 기존 develop 문서는 아직 자동 이동·삭제하지 않았다.

| 기존 원본 | 목표 명세 영역 | 현재 처리 |
| --- | --- | --- |
| frontend/docs/api-spec.md, frontend/src/types/api.ts | spec/shared/contracts/ | /me·공통 오류만 부분 이관 초안 |
| backend/docs/api-spec.md, error-reasons.md | spec/shared/contracts/ | 상충 항목을 migration.md에서 추적 |
| backend/docs/layer-rules.md, db-schema.md, pipeline.md | spec/backend/ | 현 원본 유지, architecture·기능 문서에서 참조 |
| backend/docs/testing.md, deploy.md 등 | 검수 후 관련 팀 spec 또는 실행 가이드 | 이번에 이동하지 않음 |

범위·명칭·프로토콜이 일치하고 팀 검수를 마친 문서부터 이관한다. 이관 완료 시 기존 위치는 링크 안내로 대체하여 원본을 하나로 유지한다.
원본 이관 전에는 새 spec을 전체 구현의 최종 기준으로 선언하지 않는다.
