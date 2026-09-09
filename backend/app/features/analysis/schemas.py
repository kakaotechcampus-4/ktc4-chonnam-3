"""분석 요청/응답 스키마.
★ 분석 실패는 HTTP 200 + failureReason (4xx 를 내면 FE 의 queryCache.onError 가 걸린다).
★ failureReason 은 BE 내부명을 그대로 쓴다 (FE 합의) — jd_fetch_failed /
  jd_extraction_failed / token_invalid. 경계 매핑 레이어를 두지 않는다.
⚠ 미결 — analysis_jobs.status='partial'(10개 중 8개 성공) 을 FE 에 무엇으로 내려보낼지.
  docs/error-reasons.md '미결' 절 참조.

확정본 §3 / task-04
"""
