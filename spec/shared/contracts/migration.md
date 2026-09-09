# 계약 이관 현황 — 2026-09-09 develop 조회 기준

이 문서는 충돌을 추적한다. 기존 자료의 내용을 팀의 새 합의로 바꾸지 않는다.

| 항목 | 현재 자료 | 초안 처리 | 검수·승격 조건 |
| --- | --- | --- | --- |
| GET /me | FE 문서·MeResponse | 부분 OpenAPI + schema | FE·BE 필드/상태코드 확인, 실제 구현 테스트 |
| 에러 봉투 | FE ApiError·BE error-reasons | 공통 구조만 schema | retryAfter optional, reason registry 검토 |
| Persona | FE tech_lead/senior_developer/manager; BE 문서 tech_lead/hr_manager/domain_lead | enum 새로 생성하지 않음 | FE·AI 반영 시점 확인 |
| 분석 StepKey | FE 4개; BE 문서 7개 | 이관 대기 | FE·BE·AI 단계 의미·표시 합의 |
| 에러 reason | FE 구 이름; BE 문서 token_invalid 등 | reason은 string 유지 | 레지스트리 원본과 FE 표시 동시 갱신 |
| WebSocket | FE 오디오·transcript; BE 문서 스프린트1 텍스트 | 메시지 schema 생성 보류 | 클라이언트 답변 메시지·오디오 제거 범위 확정 |
| 부분 실패 | BE 내부 partial; FE RunStatus 3값 | 매핑 미확정 표시 | counts/failedRepositories 제안 채택 여부 |
| AI 배치 | 현재 backend/app/agents·llm_tasks | spec/ai 명세·ai/CLAUDE.md 지침만 추가 | 코드 이동·별도 배포는 별도 결정 |
| 모델·저장소 | pyproject에 anthropic 의존성 있음 | 모델 선정으로 해석하지 않음 | 실제 모델·provider·RAG 저장소 팀 확인 |

검수 전 API 판단: FE 문서·타입을 기본으로 보되 BE의 합의 변경표를 함께 읽는다. 불일치 시 단독으로 구현 기준을 확정하지 않는다.

참고 원본: frontend/docs/api-spec.md, frontend/src/types/api.ts, backend/docs/api-spec.md, backend/docs/error-reasons.md.
