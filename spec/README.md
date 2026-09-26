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
공통 API의 원본 구분은 [현행 계약 안내](shared/contracts/README.md)와 병합된 [PR #35](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/35)를 따른다. 일반 API 요청·응답은 `spec/shared/contracts/openapi.yaml`, WebSocket·SSE·브라우저 이동 경로는 `frontend/docs/api-spec.md`가 기준이다. 기존 문서는 자동 이동·삭제하지 않는다.

| 기존 원본 | 목표 명세 영역 | 현재 처리 |
| --- | --- | --- |
| frontend/docs/api-spec.md | spec/shared/contracts/ | 일반 API는 OpenAPI 기준. WebSocket·SSE·브라우저 이동 경로는 기존 FE 문서가 원본 |
| frontend/src/types/api.ts | 공통 API 계약을 사용하는 FE 구현 타입 | 별도 계약 원본이 아니며 현행 공통 계약에 맞춰 검증 |
| backend/docs/api-spec.md, error-reasons.md | spec/shared/contracts/ | 공통 계약과 다른 부분은 현행 원본을 우선하며 개별 충돌·보류는 migration.md에서 추적 |
| backend/docs/layer-rules.md, db-schema.md, pipeline.md | spec/backend/ | 현 원본 유지, architecture·기능 문서에서 참조 |
| backend/docs/testing.md, deploy.md 등 | 검수 후 관련 팀 spec 또는 실행 가이드 | 이번에 이동하지 않음 |

아직 원본으로 유지하는 DB·pipeline·운영 등의 문서는 범위·명칭·프로토콜이 일치하고 팀 검수를 마친 뒤 이관한다. 이관 완료 시 기존 위치는 링크 안내로 대체한다.
API 기준 문서가 정해진 것과 전체 문서 이관·기능 구현·검증 완료는 구분한다. 개별 보류와 구현 상태는 [계약 이관 현황](shared/contracts/migration.md) 및 관련 기능·검증 문서에서 확인한다. 과거의 `/me`·공통 오류만 이관하는 초안은 [결정 이력](shared/decisions/0001-contract-migration.md)으로 보존한다.
