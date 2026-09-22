# task-12 — SSE 진행 스트림

> 선행: task-11
> 근거: `backend/docs/pipeline.md`, `backend/docs/redis-keys.md`

## 목표

분석 run 진행 상태 SSE와 Redis mirror를 구현한다.

## 작업

- `run:{runId}:steps` Redis mirror를 사용한다.
- SSE 접속 시 `run:{runId}:events` 구독이 성립한 것을 확인한 뒤 Postgres에서 현재 상태를 읽어 보낸다. Redis mirror를 초기 상태의 원본으로 사용하지 않는다.
- 구독 이후 받은 이벤트를 이어서 전달하며 같은 step의 같은 상태는 중복 제거한다.
- Postgres commit 완료 -> Redis mirror -> publish 순서를 지킨다. 저장 후 Redis 갱신·알림만 실패하면 DB 결과를 유지한다.
- 종료 상태를 확인할 때까지 Postgres를 주기적으로 재확인해 Pub/Sub 알림 유실에 대비한다.
- 15초 keep-alive comment를 보낸다.
- 종료 run은 마지막 상태를 보내고 stream을 닫는다.

## 완료 조건

- 재접속 시 현재 step 상태를 즉시 받을 수 있다.
- 구독과 초기 조회 사이에 run이 종료돼도 완료·실패 상태를 놓치지 않는다.
- Redis mirror가 오래됐거나 알림이 유실돼도 Postgres 원본으로 상태를 확인한다.
- publish 순서 때문에 DB 조회가 뒤처지는 케이스가 없다.
