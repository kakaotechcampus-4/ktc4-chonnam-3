# task-07 — /me 계열 API

> 선행: task-06
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`/me/home`, `/me/interviews`. `analysisStatus` 파생 로직 포함.

## 확정본 반영 (설계 초기안 대비 변경)

- `user_profile_summaries.based_repo_ids` 를 **정렬해서 저장**한다 — 재생성 판정 키라서 순서가 흔들리면 매번 재생성된다.
- `role_summary` 만 LLM 산출물(`llm_tasks/profile_summary.py`), 나머지는 확정 레포의 `languages` / `project_types` 집계.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
