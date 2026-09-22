# API 스펙 구현 기준

일반 REST/fetch API 계약의 원본은 `spec/shared/contracts/openapi.yaml`이다. WS·SSE·브라우저 이동 경로는 `frontend/docs/api-spec.md`를 따른다. 범위 구분은 [공통 계약 안내](../../spec/shared/contracts/README.md)가 원본이며, 이 파일은 백엔드 구현자가 읽는 보조 설명이다.

## 원칙

- API field는 camelCase.
- Python/Pydantic 내부와 DB는 snake_case.
- 모든 4xx/5xx는 `error.reason`, `error.message`, `error.details` envelope를 사용한다.
- 일반 REST/fetch API가 FE 문서와 충돌하면 `spec/shared/contracts/openapi.yaml`을 우선한다. WS·SSE·브라우저 이동 경로는 위 예외 구분을 유지한다.
- `PENDING_*` 항목은 임의로 확정하지 않는다.

## Sprint 1 주요 API

| API | 역할 |
| --- | --- |
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

## 보류

- unmatched portfolio GitHub URL 사용자 노출.
- feedback disagreement API는 Sprint 2.
