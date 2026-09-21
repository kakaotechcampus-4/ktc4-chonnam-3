# API 스펙 구현 기준

공통 API 계약의 원본은 `spec/shared/contracts/openapi.yaml`이다. 이 파일은 백엔드 구현자가 읽는 보조 설명이다.

## 원칙

- API field는 camelCase.
- Python/Pydantic 내부와 DB는 snake_case.
- 모든 4xx/5xx는 `error.reason`, `error.message`, `error.details` envelope를 사용한다.
- FE 문서와 충돌하면 `spec/shared/contracts/openapi.yaml`을 우선한다.
- `PENDING_*` 항목은 임의로 확정하지 않는다.

## Sprint 1 주요 API

| API | 역할 |
| --- | --- |
| `GET /auth/github/login` | GitHub OAuth 시작, state/PKCE 저장 후 302 |
| `GET /auth/github/callback` | 로그인 완료 후 `/home`, 안전한 실패 reason은 `/login`으로 302 |
| `POST /auth/refresh` | Origin 검증 후 PostgreSQL refresh session 트랜잭션 rotation, 204 |
| `POST /auth/logout` | 현재 refresh sid 폐기와 cookie 삭제, 204 |
| `GET /me` | `{name, avatarUrl, githubLinked}` 인증 identity |
| `POST /documents/preview` | 포트폴리오 텍스트와 GitHub URL preview. claim 추출 없음 |
| `POST /analysis-runs` | Wanted 공고 기반 분석 run 시작 |
| `GET /analysis-runs/{runId}` | run 진행 상태 조회 |
| `GET /analysis-runs/{runId}/events` | SSE 진행 이벤트 |
| `GET /analysis-runs/{runId}/result` | 첫 batch 추천 결과 |
| `GET /analysis-runs/{runId}/candidates?page=N` | 후보 page 분석/조회 |
| `POST /interviews` | 면접 생성 및 `interview_prep` enqueue |
| `GET /interviews/{id}` | 면접 상세/준비 상태 조회 |
| `POST /interviews/{id}/prepare/retry` | 준비 실패 후 REST 재시도 |
| `GET /ws/interviews/{sessionId}` | 텍스트 WS |
| `GET /interviews/{id}/report` | lazy report generation 및 조회 |
| `POST /interviews/{id}/retry` | 원본 입력 복사 재면접 |

refresh/logout은 PostgreSQL을 사용하며 Redis를 조회하지 않는다. 유효한 토큰에 대한 DB 장애는 503으로 구분하고 쿠키 삭제·폐기 성공으로 응답하지 않는다. OAuth state는 계속 Redis를 사용한다. 기존 Access JWT는 logout 후에도 최대 15분간 유효하다.

## 보류

- unmatched portfolio GitHub URL 사용자 노출.
- feedback disagreement API는 Sprint 2.
