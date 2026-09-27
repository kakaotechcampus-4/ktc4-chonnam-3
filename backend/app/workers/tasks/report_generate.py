"""report 조회 시 조건을 만족하면 enqueue하는 lazy 생성 태스크의 구현 예정 경계.
features/report 로직을 호출하고 성공 뒤 profile_summary를 enqueue한다.
면접 종료만으로 자동 생성하지 않으며 재생성·수동 재시도는 Sprint 2다.

docs/layer-rules.md 1절 / task-16
"""
