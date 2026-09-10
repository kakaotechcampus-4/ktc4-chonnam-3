# task-04 — 스키마 · 계약 테스트

> 선행: task-02
> 근거: `spec/shared/contracts/openapi.yaml`

## 목표

Pydantic schema와 공통 계약 테스트를 만든다.

## 작업

- `CamelModel`을 공통 base로 두고 API request/response를 camelCase로 직렬화한다.
- Python 필드는 snake_case로 유지한다.
- `RunStatus`: `running`, `completed`, `failed`.
- `StepKey`: `doc_extract`, `repo_select`, `repo_detail`, `jd_fetch`, `jd_extract`, `repo_analyze`, `match_score`.
- `Persona`: `tech_lead`, `hr_manager`, `domain_lead`.
- `DocumentExtractStatus`: `succeeded`, `partial`, `failed`.
- 계약 테스트에서 응답에 snake_case key가 새지 않는지 확인한다.

## 완료 조건

- OpenAPI와 Pydantic schema의 required/nullable/enum이 일치한다.
- FE 보류 항목은 `PENDING_FE` 설명으로 남기고 임의 제거하지 않는다.
