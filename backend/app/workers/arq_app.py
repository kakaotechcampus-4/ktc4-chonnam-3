"""ARQ WorkerSettings — 큐 정의, 재시도, 타임아웃.

등록 태스크 4종 —
  initial_sync    (M1)   연동 직후 L0-a 수집
  interview_prep  (M2)   7 step
  deep_analysis   (M4-a) 확정 레포 L2
  report_generate (M6)   면접 종료 → 리포트

becontext.md §7.1 / task-11
"""
