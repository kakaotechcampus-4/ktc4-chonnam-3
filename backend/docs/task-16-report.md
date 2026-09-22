# task-16 — 리포트 · 프로필 요약

> 선행: task-15
> 근거: `spec/backend/features/report.md`

## 목표

Lazy report generation과 profile summary 후속 갱신을 구현한다.

## 작업

- `GET /interviews/{id}/report`가 report 존재 시 200을 반환한다.
- report가 없고 생성 가능하면 `report_generate` enqueue 후 202를 반환한다. 생성 가능 조건은 `status='completed'`이고 답변 완료 turn이 1개 이상인 경우다.
- 생성 중 lock이 있으면 중복 enqueue 없이 202를 반환한다.
- 생성 불가, 답변 완료 turn 0개, 또는 이전 생성 실패 이력이 있으면 `409 report_unavailable`. 리포트 재생성·수동 재시도·이의제기 기반 재평가는 Sprint 2다.
- report 성공 후 `profile_summary` job을 enqueue한다.
- profile summary 갱신은 report 응답을 막지 않는다. 실패 재시도·복구·상세 실패 처리는 Sprint 2로 넘긴다.
- profile 언어 집계는 [0016 결정](../../spec/ai/decisions/0016-profile-language-aggregation.md)을 따른다. 완료 면접의 저장소를 중복 제거하고 기존 저장소별 언어 비율을 같은 비중으로 평균내며 저장소 수·공개 필드·기존 저장 구조를 유지한다.
- [0019 결정](../../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 Sprint 1 개인 역할 요약을 LLM으로 생성하는 기존 계획을 복원한다. 기존 `user_profile_summaries.role_summary`·`roleSummary`와 Home 표시·후속 갱신 흐름을 유지한다. 언어·유형 집계에는 LLM을 사용하지 않고, 역할 요약에서 근거 없는 개인 기여를 만들어내거나 프로젝트 설명을 개인 역할로 단정하지 않는다. 실제 생성·저장·호출은 구현 대상이며 새 DB/API 필드를 추가하지 않는다.
- persona별 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_disagreements`는 Sprint 1 테이블 생성 대상이며 실제 migration 적용은 별도 검증한다. API/row 생성은 Sprint 2로 넘긴다.
- 점수는 0~100 number 6개와 단순 평균 `totalScore`를 반환한다. 가중치와 nullable/status 표현은 사용하지 않는다.

## 완료 조건

- 200/202/409 흐름과 중복 lock을 테스트한다.
- profile summary job enqueue가 report 성공 후 발생한다. 역할 요약 생성이 실패해도 이미 성공한 report를 실패로 되돌리지 않는다.
- 역할 요약의 근거와 표현을 검증하고 LLM 출력으로 언어·유형 집계를 변경하지 않는다.
- 같은 repo를 여러 면접·ref에서 사용해도 비중이 늘지 않는다. Python 100% repo와 Java 100% repo를 합치면 각각 50%이며 언어 자료 누락을 0%로 꾸미지 않는다.
