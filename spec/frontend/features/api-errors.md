# API 오류 처리 — 검수 초안
- 상태: 기존 구현 검토용 요구사항. 구현 완료 아님.
- 코드: frontend/src/shared/api.ts
- 계약: spec/shared/contracts/api-error.schema.json, frontend/docs/api-spec.md

## 기대 동작
- 정상 JSON 응답과 204 빈 응답을 구분.
- 계약에 맞는 오류에서 reason/message/retryAfter 보존.
- HTML·빈 body·잘못된 JSON 오류는 파싱 실패에 가리지 않고 합의된 사용자 오류로 처리.
- 네트워크 실패와 HTTP 실패를 구분.
- 분석 status=failed는 HTTP 실패와 구분.

## 검수
기존 api.ts와의 동작 차이, fallback 문구, reason 변경 여부를 검수 기록에 남긴다. 공통 응답 규격 변경에는 관련 팀 합의가 필요하다.
테스트 도구 선정 전에는 수동 검증 시나리오와 결과를 기록한다. lint/build를 동작 테스트로 대체하지 않는다.
