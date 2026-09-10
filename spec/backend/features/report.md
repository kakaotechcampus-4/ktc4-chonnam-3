# 리포트와 프로필 요약

상태: Sprint 1 FIX + 점수 산정 `PENDING_TEAM`.

## 생성 방식

리포트는 lazy generation이다.

`GET /interviews/{id}/report`

- 이미 생성된 리포트가 있으면 `200`.
- 없고 생성 가능하면 `report_generate` ARQ job을 enqueue하고 `202 { "status": "generating", "retryAfter": 3 }`.
- 이미 생성 중이면 중복 enqueue 없이 `202`.
- 생성 불가면 `409 report_unavailable`.

면접 종료 직후 자동 enqueue하지 않는다. 화면 진입 시 생성해도 체감 속도 차이가 작고, race condition을 줄일 수 있다.

## Profile Summary

`report_generate` job이 성공하면 `profile_summary` job을 후속 enqueue한다.

- 리포트 API 응답은 profile summary 갱신을 기다리지 않는다.
- 같은 사용자에 대해 진행 중인 profile summary job이 있으면 중복 enqueue를 막는다.
- Sprint 1은 단순 집계 중심.
- Sprint 2는 LLM 기반 자연어 요약을 강화한다.

`user_profile_summaries`는 Sprint 1 DB에 포함한다. 집계 기준은 전체 수집 repo가 아니라 완료된 면접에 사용된 repo다.

## 점수

리포트 API에는 `totalScore`, `scores[].score`가 필요하다. 내부 루브릭은 1~5 기준의 흔적이 있다. 실제 점수 산정 근거와 0~100/1~5 저장 방식은 `PENDING_TEAM`.

Sprint 1 구현은 API shape, 리포트 생성 상태, persona별 feedback JSON, evidence 연결 구조를 우선한다. 점수 산정 공식은 팀 확정 전까지 문서에서 임의 고정하지 않는다.

## Feedback JSON

persona별 피드백은 별도 `report_persona_feedbacks` 테이블을 만들지 않고 `interview_reports.feedback_json`에 저장한다.

## Feedback Disagreement

`report_disagreements` 테이블은 Sprint 1 migration에 포함한다. 다만 Sprint 1에서는 API를 열지 않고 row도 생성하지 않는다.

Sprint 2에서 사용자 이의제기 기능을 구현할 때 API와 `(report_id, persona)` 중복 방지 제약을 사용한다.
