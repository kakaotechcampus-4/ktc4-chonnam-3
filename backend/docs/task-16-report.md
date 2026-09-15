# task-16 — 리포트 · 프로필 요약

> 선행: task-15
> 근거: `spec/backend/features/report.md`

## 목표

Lazy report generation과 profile summary 후속 갱신을 구현한다.

## 작업

- `GET /interviews/{id}/report`가 report 존재 시 200을 반환한다.
- report가 없고 생성 가능하면 `report_generate` enqueue 후 202를 반환한다. 생성 가능 조건은 `status='completed'`이고 답변 완료 turn이 1개 이상인 경우다.
- 생성 중 lock이 있으면 중복 enqueue 없이 202를 반환한다.
- 생성 불가, 답변 완료 turn 0개, 또는 이전 생성 실패 이력이 있으면 `report_unavailable`. Sprint 1에서는 자동 재생성하지 않는다.
- report 성공 후 `profile_summary` job을 enqueue한다.
- profile summary 갱신은 report 응답을 막지 않는다. 실패 재시도·복구·상세 실패 처리는 Sprint 2로 넘긴다.
- persona별 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_disagreements` 테이블은 Sprint 1 migration에 존재하지만 API/row 생성은 Sprint 2로 넘긴다.
- 점수는 0~100 number 6개와 단순 평균 `totalScore`를 반환한다. 가중치와 nullable/status 표현은 사용하지 않는다.

## 완료 조건

- 200/202/409 흐름과 중복 lock을 테스트한다.
- profile summary job enqueue가 report 성공 후 발생한다.
