# task-05 — 에러 규약

> 선행: task-01
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`AppError` + 전역 핸들러 3개 + `docs/error-reasons.md`.

## 확정본 반영 (설계 초기안 대비 변경)

- 에러가 **3계층**으로 확정됐다 — `analysis_jobs.error_code`(작업) / `repo_analyses.error_code`(레포 1개) / `job_postings.parse_error_code`(공고 1건).
- 10개 중 3개 실패는 job `succeeded` + 개별 row `failed` 다. 층을 섞으면 전체를 실패 처리하게 된다.
- `stt_failed` / `tts_failed` 는 스프린트2.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
