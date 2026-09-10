# BE 검수·완료 기준

상태: Sprint 1 FIX.

## 필수 검증

| 영역 | 기준 |
| --- | --- |
| 계약 | `spec/shared/contracts/openapi.yaml`과 Pydantic schema가 camelCase API를 일치시킨다 |
| 에러 | 모든 4xx/5xx는 공통 error envelope를 반환한다 |
| DB | PostgreSQL 기준 migration이 CHECK, UNIQUE, INDEX, JSONB, TEXT[], pgcrypto를 포함한다 |
| 분석 | 7 step 상태 전이, partial->FE failed 매핑, result 조회 가능 조건을 검증한다 |
| 후보 | `analysis_repo_candidates` ranking, excluded reason, page 분석 상태를 검증한다 |
| 문서 | preview 지원 형식, 크기 제한, GitHub URL 정규화, 실패 후 계속 진행을 검증한다 |
| GitHub | public repo만 수집/분석하고 private는 제외한다 |
| Wanted | Sprint 1은 Wanted-only이며 unsupported site를 차단한다 |
| 면접 | 9턴, 첫 hr_manager 질문, persona target distribution, 텍스트 WS를 검증한다 |
| Evidence | `question_basis`와 `evaluation_basis`, `answer_vs_code` conflict 생성을 검증한다 |
| Redis | Redis snapshot 유실 시 Postgres에서 재구성 가능해야 한다 |
| 리포트 | lazy generation 200/202/409, feedback disagreement unique를 검증한다 |
| 이벤트 | 고정 10개 이벤트 외 값은 거부한다 |

## 테스트 원칙

- GitHub, Wanted, LLM은 mock한다.
- DB 기능은 SQLite로 대체하지 않고 PostgreSQL 기준으로 검증한다.
- LLM JSON parsing 실패는 1회 재시도 후 실패 처리하고 raw output을 남긴다.
- 리포트 점수 산정은 `PENDING_TEAM`이므로 shape와 상태 중심으로 검증한다.

## 완료 보고

Claude는 아래 명령을 실행하거나, 실행하지 못한 이유를 보고해야 한다.

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```
