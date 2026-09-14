# task-13 — 면접 REST

> 선행: task-11
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`POST /interviews`, `GET /interviews/{id}`, `/retry` + `sessionId` 발급.

## 확정본 반영 (설계 초기안 대비 변경)

- `job_posting_id` 가 **NOT NULL** 이다 (공고 필수).
- `status` = `preparing` / `in_progress` / `completed` / `abandoned`. **`paused` 없음 — 세션 재개 미지원.**
- 이탈은 `abandoned` + `abandoned_at_turn`. 미답변 턴은 `asked` 로 남긴다 (1차에 `timeout` 판정 배치를 만들지 않는다).
- ⚠ `job_posting_id` NOT NULL 과 `unsupported_site` 의 "공고 없이 진행 유도" 가 충돌한다 — [db-schema.md](db-schema.md) 미결 절.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
