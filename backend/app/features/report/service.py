"""리포트 lazy 생성·조회(200/202/409)의 구현 예정 경계.
완료 면접에 답변 완료 턴이 있고 이전 생성 실패가 없을 때만 생성한다.
생성 불가·실패 이력은 409 report_unavailable. 재생성·수동 재시도·이의제기는 Sprint 2다.
성공 후 profile_summary를 enqueue하며 프로필 실패는 리포트 성공을 되돌리지 않는다.

docs/db-schema.md 리포트 절 / task-16
"""
