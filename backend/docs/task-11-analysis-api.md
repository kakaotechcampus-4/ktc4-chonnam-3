# task-11 — 분석 API · 큐 배선

> 선행: task-08, task-09, task-10
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`POST /analysis-runs` (multipart) + ARQ 배선 + `GET /analysis-runs/{runId}` / `/result`.

## 확정본 반영 (설계 초기안 대비 변경)

- 파이프라인이 **`job_type` 3종**으로 갈렸다 — `features/analysis/pipeline/{initial_sync,interview_prep,deep_analysis}.py`, 워커 태스크도 3개.
- `interview_prep` 은 **7 steps** — `doc_extract` → `repo_select` → `repo_detail` → `jd_fetch` → `jd_extract` → `repo_analyze` → `match_score`.
- 중복 방지가 `(user_id, job_type)` 단위다. M1 은 연동 직후 백그라운드라 M2 와 겹친다 — 사용자 단일 락으로 두면 정상 흐름이 `run_in_progress` 로 막힌다.
- `status` 6값. `partial` 은 작업이 끝났고 결과도 있지만 후보 일부가 빠진 상태다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
