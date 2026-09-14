"""run 생성 / 중복 방지 / 만료 판정.
★ job_type 3종(initial_sync / interview_prep / deep_analysis) 별로 중복을 막는다 —
  DB 부분 유니크가 (user_id, job_type) WHERE status IN ('queued','running') 이고
  Redis 락도 run:lock:{userId}:{jobType} 다. M1 은 연동 직후 백그라운드라 M2 와 겹친다.
★ status = queued / running / succeeded / partial / failed / canceled.

확정본 §3 analysis_jobs / task-11
"""
