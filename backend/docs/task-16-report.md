# task-16 — 리포트

> 선행: task-15
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`report_generate` 워커 + `GET report` (202 포함) + `feedback-disagreements`.

## 확정본 반영 (설계 초기안 대비 변경)

- 채점 시 `turn_evidences` 에 `usage=evaluation_basis` 를 남긴다.
- 커버리지는 `context_state.covered_requirement_ids` / `covered_claim_ids` 에서 산출한다.
- ⚠ 리포트 4테이블은 컬럼 확정본이 아직 없다 — [db-schema.md](db-schema.md) 의 "리포트 — 잠정 결정" 절 기준.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
