# task-02 — DB 모델 · 초기 마이그레이션

> 선행: task-01
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

1차 테이블 전체 모델 + `0001_initial` 마이그레이션. `pgcrypto` 확장 포함.

## 확정본 반영 (설계 초기안 대비 변경)

- **`document_claims` 가 1차 포함**으로 바뀌었다 (설계 초기안의 "1단계 제외" 폐기). 1차 컬럼 5개만 채우고 `topic_code`·`repository_hint` 는 2차.
- `analysis_jobs` 에 **`job_type`** 3종 + `status` 6값(`partial`·`canceled` 추가).
- `repositories` 에 `fetch_level`(`list`/`detail`), `repo_analyses` 에 `analysis_level`(`shallow`/`deep`).
- `interview_turns.topic_code` 는 **1차에 FK 를 걸지 않는다**.
- `interview_turns` 에 `transcript_confidence` / `audio_uri` 를 **만들지 않는다** (스프린트2).
- `interview_sessions` 에 `CHECK (answer_mode = text)`.
- persona CHECK = `tech_lead` / `hr_manager` / `domain_lead`.
- `github_accounts.token_status`, `users.status` / `last_login_at` 추가.
- `auth_sessions` 는 만들지 않는다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
