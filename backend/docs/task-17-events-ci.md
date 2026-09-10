# task-17 — 지표 · CI · 배포

> 선행: task-16
> 근거: `spec/backend/verification.md`

## 목표

최소 이벤트 10종, 품질 지표 쿼리, CI 검증을 구현한다.

## 작업

- events table은 event_name을 `VARCHAR + CHECK`로 제한한다.
- Sprint 1 이벤트: `analysis_run_started`, `analysis_run_completed`, `analysis_run_failed`, `repo_recommended`, `repo_selected`, `interview_started`, `turn_asked`, `turn_answered`, `interview_completed`, `report_viewed`.
- `interview_abandoned`는 `PENDING_FE`.
- 이벤트 기록 실패는 핵심 트랜잭션을 실패시키지 않는다.
- 지표 쿼리: 평균 depth, evidence tool 사용 비율, `selection_source=ai_removed` 목록, report_viewed count.
- CI는 ruff, format check, mypy, pytest를 실행한다.

## 완료 조건

- 고정 10개 밖의 event_name insert가 거부된다.
- CI 명령 실행 결과를 PR에 남긴다.
