# 사전 분석 실행 — 검수 초안
- 상태: 기능 경계·검증 기준 초안.
- 기존 문서: backend/docs/pipeline.md, db-schema.md, api-spec.md, error-reasons.md
- 현재 코드 영역: backend/app/features/analysis, workers, llm_tasks

## 입력·출력
입력은 기존 POST /analysis-runs 명세를 확인. 출력은 runId와 조회 가능한 진행 상태.
선택 저장소의 입력 시점은 현재 FE 흐름과 사용자 서비스 기획을 대조하여 검수한다.

## 완료 조건
- 접수·중복 요청·파일 제한·만료의 계약과 테스트 일치.
- HTTP 실패와 run 실패를 구분.
- 부분 실패의 상태 매핑과 카드 정보는 migration 안건 확정 후 구현.
- 큐·DB·Redis·LLM 사이의 실패·재시도 경계 검증.
구현과 실행 검증은 별도 작업이며 이 문서로 완료 처리하지 않는다.
