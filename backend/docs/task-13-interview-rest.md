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
- `/interviews/{id}/retry`는 completed/abandoned 원본만 허용하고 원본 입력을 복사한다.
- WS 식별자 정책은 `PENDING_FE`로 유지한다.

## 완료 조건

- invalid repository, too many, no selected, session limit, retry 상태 제한을 테스트한다.
