# task-05 — 에러 규약

> 선행: task-01
> 근거: `backend/docs/error-reasons.md`

## 목표

`AppError`, 전역 exception handler, reason registry를 구현한다.

## 작업

- 모든 4xx/5xx 응답을 `{error:{reason,message,details}}`로 감싼다.
- `HTTPException` 직접 raise를 금지한다.
- `RequestValidationError`는 계약 envelope로 변환한다.
- 인증, 문서, 분석, 후보, 면접, 리포트 reason을 registry에 정의한다.
- 내부 job error_code와 API reason을 구분한다.
- DB `partial`은 API `RunStatus.failed`로 매핑한다.

## 완료 조건

- 대표 400/401/403/409/413/415/500 테스트가 envelope shape를 검증한다.
- 알 수 없는 exception은 `internal_error`로 반환된다.
