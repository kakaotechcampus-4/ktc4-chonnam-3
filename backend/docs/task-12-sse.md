# task-12 — SSE 진행 스트림

> 선행: task-11
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

`/analysis-runs/{runId}/events` + `run:*` Redis 키 배선.

## 확정본 반영 (becontext.md 대비 변경)

- 락 키가 `run:lock:{userId}:{jobType}` 로 바뀌었다.
- 레포 분석 캐시 키에 `level` 과 `headSha` 가 들어간다 — 기존 키로는 shallow/deep 이 서로를 덮고 push 후에도 캐시가 히트한다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
