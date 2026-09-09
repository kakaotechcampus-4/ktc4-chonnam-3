# task-10 — 레포 매칭

> 선행: task-08, task-09
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`match_score` step → `repo_match_scores`.

## 확정본 반영 (설계 초기안 대비 변경)

- **`is_ai_recommended` 를 5개 이하로 제한한다.** `is_selected` 상한이 5라, 8개를 추천하면 채택률이 구조적으로 62.5% 를 못 넘어 지표가 처음부터 망가진 채 쌓인다. 테스트로 고정한다.
- `candidate_source`(`rule_filter` / `portfolio` / `both`) → M3 카드의 포트폴리오 배지.
- `matched_requirement_ids` 는 M6 커버리지 계산 입력이다.
- 정성 분석의 실제 입력은 채택률 숫자가 아니라 `selection_source=ai_removed` 목록이다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
