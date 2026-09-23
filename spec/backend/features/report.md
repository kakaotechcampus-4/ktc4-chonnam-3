# 리포트와 프로필 요약

상태: Sprint 1 FIX. 점수 세부 기준 seed는 평가 자료 보강에 따라 갱신 가능.

## 생성 방식

리포트는 lazy generation이다.

`GET /interviews/{id}/report`

- 이미 생성된 리포트가 있으면 `200`.
- 없고 생성 가능하면 `report_generate` ARQ job을 enqueue하고 `202 { "status": "generating", "retryAfter": 3 }`.
- 이미 생성 중이면 중복 enqueue 없이 `202`.
- 생성 불가면 `409 report_unavailable`.

생성 가능 조건:

- `interview_sessions.status='completed'`.
- 답변 완료 turn이 1개 이상.
- `abandoned`, `preparing`, `preparing_failed`, `in_progress`는 생성 대상이 아니다.
- 이전 `report_generate` 실패 이력이 있으면 Sprint 1에서는 자동 재생성하지 않고 `409 report_unavailable`로 응답한다. 리포트 재생성·수동 재시도·이의제기 기반 재평가는 Sprint 2다.

면접 종료 직후 자동 enqueue하지 않는다. 화면 진입 시 생성해도 체감 속도 차이가 작고, race condition을 줄일 수 있다.

## Profile Summary

`report_generate` job이 성공하면 `profile_summary` job을 후속 enqueue한다.

- 리포트 API 응답은 profile summary 갱신을 기다리지 않는다.
- 같은 사용자에 대해 진행 중인 profile summary job이 있으면 중복 enqueue를 막는다.
- Sprint 1 언어·프로젝트 유형은 기존 자료로 집계하고, 개인 역할 요약만 LLM으로 생성한다.
- profile summary 실패는 이미 생성된 report를 실패로 되돌리지 않는다. 실패 재시도·복구·상세 실패 처리는 Sprint 2다.
- Sprint 2는 LLM 기반 자연어 요약을 강화한다.

`user_profile_summaries`는 Sprint 1 DB에 포함한다. 집계 기준은 전체 수집 repo가 아니라 완료된 면접에 사용된 repo다.

[0016 결정](../../ai/decisions/0016-profile-language-aggregation.md)에 따라 기존 저장소 식별자로 중복을 제거하며 같은 저장소의 면접 횟수·ref 수로 비중을 늘리지 않는다. `basedOnRepoCount`는 서로 다른 대상 저장소 수이고, `languages`는 기존 저장소별 언어 비율의 동일 비중 평균이다. 코드량 가중치·추가 수집·ref별 새 스냅샷 저장을 요구하지 않는다. 언어 자료 자체가 누락된 저장소를 0%로 넣거나 제외해 성공 결과를 만들지 않고 기존 갱신 실패 경계에서 이전 성공 요약을 유지한다.

[0019 결정](../../ai/decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 Sprint 1 개인 역할 요약 보류를 철회하고 기존 LLM 요약 계획을 복원한다. 기존 `user_profile_summaries.role_summary` 저장 필드와 `roleSummary` 응답, Home 표시, `profile_summary(user_id)` 후속 갱신과 실패 분리를 유지한다. 언어·유형 집계에 LLM을 사용하지 않으며, 역할 요약은 기존 근거가 뒷받침하는 범위에서 작성하고 프로젝트 기능·README·commit만으로 개인 기여를 단정하지 않는다. 새 DB/API 필드는 추가하지 않는다. 실제 요약 생성·저장·호출 연결은 아직 구현·검증 대상이다.

## 점수

리포트 API에는 `totalScore`, `scores[].score`가 필요하다. Sprint 1은 점수를 반드시 포함한다.

- `totalScore`와 `scores[].score`는 0~100 number다.
- score key는 `project_understanding`, `technical_reasoning`, `problem_solving`, `communication`, `contribution_clarity`, `company_job_fit` 6개를 유지한다.
- `totalScore`는 6개 항목 score의 단순 평균이다.
- 가중치, nullable score, status 기반 미계산 표현은 Sprint 1에 사용하지 않는다.
- 항목별 세부 평가 기준과 `score_criteria` seed 문구는 평가 담당자가 자료를 보강하며 갱신할 수 있다.

## Feedback JSON

persona별 피드백은 별도 `report_persona_feedbacks` 테이블을 만들지 않고 `interview_reports.feedback_json`에 저장한다.

## Feedback Disagreement

`report_disagreements` 테이블은 Sprint 1 migration에 포함한다. 다만 Sprint 1에서는 API를 열지 않고 row도 생성하지 않는다.

Sprint 2에서 사용자 이의제기 기능을 구현할 때 API와 `(report_id, persona)` 중복 방지 제약을 사용한다.
