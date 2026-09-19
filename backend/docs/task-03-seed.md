# task-03 — 도메인 지식 시드

> 선행: task-02
> 근거: `spec/backend/features/interview.md`

## 목표

prompt version, domain question frame, score criteria 초기 데이터를 넣는다.

## 작업

- domain category seed: `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`.
- domain별 question frame 3개씩 seed한다.
- frame 축은 개인정보/민감정보, 장애/신뢰성/운영, 사용자 경험/서비스 사용 맥락이다.
- Sprint 1 LLM model은 모든 prompt version에서 `5.5 Luna`.
- prompt version은 작업별로 둔다: `repo_shallow_v1`, `repo_deep_v1`, `jd_extract_v1`, `answer_analysis_v1`, `director_v1`, `report_v1`, `profile_summary_v1`.
- score criteria는 Sprint 1에 사용한다. 공개 점수는 0~100 score 6개와 단순 평균 `totalScore`이며, 항목별 세부 기준 seed 문구는 평가 담당 자료 보강에 따라 수정 가능성을 열어둔다.
- persona, topic taxonomy, probe pattern은 별도 테이블/seed로 만들지 않는다.
- 질문 frame과 score criteria는 코드에 하드코딩하지 않는다.

## `score_criteria` 6개 확정

`score_key` 6종은 `spec/ai/features/answer-evaluation.md`/`spec/backend/features/report.md`가
이미 고정한 값이라 여기서 바꾸지 않는다: `project_understanding` · `technical_reasoning` ·
`problem_solving` · `communication` · `contribution_clarity` · `company_job_fit`.

- `weight` 컬럼 없음 — `totalScore`는 6개의 **단순 평균**(`report.md`: "가중치 ... 사용하지 않는다").
- 6개 전부 **항상 0~100 숫자**를 낸다. 근거(JD·자소서)가 부족해도 NULL로 비우지 않고, 그 부족함
  자체를 낮은 점수 근거로 삼는다 (`answer-evaluation.md`: "nullable score ... 사용하지 않는다").
- `contribution_clarity`/`company_job_fit`는 각각 자소서 주장/도메인 맥락에 기대지만, 위 이유로
  자료가 없을 때의 앵커도 "근거 없음 → 낮은 점수"로 서술한다 (NULL 분기 없음).
- ⚠ `spec/ai/features/answer-evaluation.md`(AI-L15)는 채점 산식·스케일 자체를 아직 "Proposed"로
  남겨뒀다. 여기 문구는 seed 콘텐츠(라벨·앵커 서술)만 확정하는 것이고, LLM이 이 앵커를 보고
  1~5 단계 중 하나를 고르는지 0~100을 직접 내는지는 AI-L15 승인 이후 결정된다.

각 criterion의 1/3/5점 앵커 서술은 `backend/scripts/seed_score_criteria.py`의
`SCORE_CRITERIA_SEED`를 원본으로 한다 (문서에 중복 기재하지 않는다).

## 완료 조건

- seed 재실행이 idempotent하다.
- domain frame은 팀 검수 후 데이터만 바꿔도 반영된다.
- `score_criteria` seed도 코드 재배포 없이 데이터만 바꾸면 반영된다.
