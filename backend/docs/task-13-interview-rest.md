# task-13 — 면접 REST

> 선행: task-11
> 근거: `spec/backend/features/interview.md`

## 목표

면접 생성, 조회, 재시도 REST API를 구현한다.

## 작업

- `POST /interviews`는 run당 활성 면접 1개만 허용한다.
- repositoryIds는 최소 1개, 최대 5개다.
- 선택 repo는 current run, public, accessible, eligible, L1 succeeded여야 한다.
- 성공 직후 `interview_prep`을 enqueue한다.
- `GET /interviews/{id}`는 preparing/preparing_failed/in_progress/completed/abandoned를 반환한다.
- `GET /interviews/{id}`는 재연결용 `sessionId`, `answerMode`, `prepareSteps`, `lastError`를 포함한다.
- 준비 실패 재시도는 `POST /interviews/{id}/prepare/retry`로 처리한다.
- `/interviews/{id}/retry`는 completed/abandoned 원본만 허용하고 원본 입력을 복사한다.
- WS 식별자는 `sessionId`를 사용하고 REST/report route는 `interviewId`를 사용한다.

## 완료 조건

- invalid repository, too many, no selected, session limit, retry 상태 제한을 테스트한다.

## 진행 상태

- `POST /interviews`: `queries.py`·`service.py`·`schemas.py`와 PostgreSQL 테스트 완료. 검사 기준은 `spec/backend/features/interview.md` "생성 검사 해석".
- `POST /interviews` router·앱 등록: `current_user`·`app.state.redis`를 제공하는 task-06(PR #57) 머지 후 진행.
- `session_repositories.snapshot_head_sha` 부재, `interview_prep`의 `analysis_jobs` 기록 방식: 스키마 논의 대기. 결정되면 생성 service에 반영한다.
- `GET /interviews/{id}`, `/prepare/retry`, `/retry`: 미착수.
