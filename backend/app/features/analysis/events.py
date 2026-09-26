"""SSE 스트림의 구현 예정 경계.
Redis pub/sub 구독 성립 확인 후 Postgres 현재 상태를 전송하고 후속 이벤트를 전달한다.
DB commit 뒤 알리며 중복 상태 제거와 Postgres 재확인으로 알림 유실을 보완한다.

docs/pipeline.md 3절 / task-12
"""
