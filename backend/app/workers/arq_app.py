"""ARQ WorkerSettings의 구현 예정 경계 — 큐 정의, 재시도, 타임아웃.

등록할 태스크 6종 —
  initial_sync           (M1)   연동 직후 L0-a 수집
  analysis_run           (M2)   분석 7단계
  candidate_page_analyze (M3)   추가 후보 page 분석
  interview_prep         (M4-a) primary L2·context·첫 질문 준비
  report_generate        (M6)   report 조회 시 lazy 생성
  profile_summary               report 성공 후 언어·유형 집계 및 LLM 개인 역할 요약
기본 queue 1개·단일 worker, max_tries=1로 ARQ 자동 retry를 끈다.
현재 파일과 tasks/의 옛 골격은 등록·호출 구현 완료가 아니다.

docs/pipeline.md 1절 / task-11
"""
