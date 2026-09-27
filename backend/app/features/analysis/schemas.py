"""분석 요청/응답 스키마의 구현 예정 경계.
★ run 조회는 HTTP 200에서 status와 failureReason으로 분석 실패를 표현한다.
  생성 성공은 202 {runId}, 동일 fingerprint의 진행 중 run은 409 run_in_progress와
  error.details.runId를 반환한다. 요청 오류와 run 처리 실패를 구분한다.
★ failureReason 은 BE 내부명을 그대로 쓴다 (FE 합의) — jd_fetch_failed /
  jd_extraction_failed / token_invalid. 경계 매핑 레이어를 두지 않는다.
★ DB partial은 FE failed로 매핑한다. partial 결과 조회는 허용하며
  analyzedCount, failedCount, failedRepositories를 포함한다.
★ 응답 필드·enum은 spec/shared/contracts/openapi.yaml을 따른다.

확정본 §3 / task-04
"""
