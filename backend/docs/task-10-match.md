# task-10 — 후보 Ranking · 레포 매칭

> 선행: task-08, task-09
> 근거: `spec/backend/features/analysis-run.md`

## 목표

`analysis_repo_candidates`, 첫 batch 혼합 전략, JD·L1 근거에 따른 추천 카드 연결을 구현한다. Sprint 1 숫자 점수 보류는 [0017 결정](../../spec/ai/decisions/0017-recommendation-score-deferral.md), 기존 태그 비교와 추천 대상 선정은 [0018 결정](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)을 따른다.

## 작업

- 전체 public repo에 L0-a lightweight ranking을 계산한다.
- excluded repo도 reason과 함께 저장한다.
- 첫 batch 10개는 혼합 전략으로 구성한다.
- 첫 batch 구성은 기존 0010대로 portfolio mentioned 최대 3, base rank top 최대 5, high contribution 최대 2를 중복 제거해 최대 10개로 한다. 아직 수집 전인 JD signal을 사용하지 않는다.
- batch repo만 L0-b/L1 분석 후 추천 카드로 노출한다.
- 기존 `repo_match_scores` 저장 위치와 reason·matched_requirement_ids 연결을 유지한다. Sprint 1 숫자 score는 계산하지 않고 기존 필드의 null 저장·응답 변환을 확인한다. 실제 JD 관련 근거 없이 요구사항 ID를 연결하지 않는다.
- 공고 기술 태그와 유효 L1 기술 목록이 직접 일치하는 선택 가능 저장소를 기존 run 후보 순서에서 앞 5개까지 추천한다. 모든 page를 합친 상한이며 새 점수 정렬·LLM 호출을 추가하지 않는다.
- 기술 정보가 없거나 일치하지 않으면 정상 미추천으로 두고 직접 선택을 유지한다. 개수를 채우기 위해 관련성을 추정하지 않는다.
- 현재 JD 태그는 공고 전체 목록이므로 해당 요구사항 문장에서도 일치 기술이 확인될 때만 `matched_requirement_ids`를 연결한다. 없으면 빈 목록으로 두고 이유에는 기술 관련성만 설명하며 경력·자격요건 충족을 단정하지 않는다.

## 완료 조건

- `base_rank`, `batch_no`, `batch_rank`, `selection_reason`이 검증된다.
- 기술 정보 없음·일치 없음은 정상 미추천이며, 기존 후보 순서를 유지한 run 전체 0~5개 추천과 여러 page의 합산 상한이 검증된다.
- 태그가 모든 요구사항에 복사돼 있어도 문장 근거 없는 ID는 연결하지 않고 경력 충족을 단정하지 않는다.
- 성공 카드도 matchScore 필드를 포함해 null로 반환하고 기존 추천 표시·이유·선택을 유지한다. 실패를 0점으로 바꾸지 않는다.
- 추천 갱신으로 사용자가 직접 선택·해제한 상태를 덮어쓰지 않는다. 실제 구현·검증 전에는 이 문서의 기준 채택만으로 연결 완료를 표시하지 않는다.
