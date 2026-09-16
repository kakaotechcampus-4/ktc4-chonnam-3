# task-10 — 후보 Ranking · 레포 매칭

> 선행: task-08, task-09
> 근거: `spec/backend/features/analysis-run.md`

## 목표

`analysis_repo_candidates`, 첫 batch 혼합 전략, L1 match score를 구현한다.

## 작업

- 전체 public repo에 L0-a lightweight ranking을 계산한다.
- excluded repo도 reason과 함께 저장한다.
- 첫 batch 10개는 혼합 전략으로 구성한다.
- batch 구성: portfolio mentioned 최대 3, base rank top 최대 5, JD signal 최대 2, high contribution 최대 2, 중복 제거.
- batch repo만 L0-b/L1 분석 후 추천 카드로 노출한다.
- `repo_match_scores`에 score, reason, matched_requirement_ids를 저장한다.
- AI 추천은 최대 5개 이하로 제한한다.

## 완료 조건

- `base_rank`, `batch_no`, `batch_rank`, `selection_reason`이 검증된다.
- AI 추천 5개 초과가 테스트로 막힌다.
