"""run 생성 / 중복 방지 / 만료 판정의 구현 예정 경계.
★ M2 작업명은 analysis_run. M1 initial_sync와 사용자 단일 락을 공유하지 않는다.
★ 동일 fingerprint의 queued/running run은 409 run_in_progress와 error.details.runId를
  반환한다. Redis 키는 run:lock:{userId}:analysis:{fingerprint}이며 종료 run은 새 생성을 허용한다.
★ 기존 DB 제약을 위 기준에 맞추는 잠금·동시성 처리는 구현·검증할 작업이다.
★ status = queued / running / succeeded / partial / failed / canceled.

확정본 §3 analysis_jobs / task-11
"""
