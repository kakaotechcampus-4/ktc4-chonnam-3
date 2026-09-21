# task-12 — SSE 진행 스트림

> 선행: task-11
> 근거: `backend/docs/pipeline.md`, `backend/docs/redis-keys.md`

## 목표

분석 run 진행 상태 SSE와 Redis mirror를 구현한다.

## 작업

- `run:{runId}:steps` Redis mirror를 사용한다.
- SSE 접속 시 Postgres/Redis에서 현재 상태를 먼저 보낸 뒤 Pub/Sub을 구독한다.
- Postgres update -> Redis mirror -> publish 순서를 지킨다.
- 15초 keep-alive comment를 보낸다.
- 종료 run은 마지막 상태를 보내고 stream을 닫는다.

## 완료 조건

- 재접속 시 현재 step 상태를 즉시 받을 수 있다.
- publish 순서 때문에 DB 조회가 뒤처지는 케이스가 없다.
