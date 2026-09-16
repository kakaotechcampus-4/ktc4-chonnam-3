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
| GitHub OAuth 응답 | 새 로그인은 만료형 token pair·유효 TTL·`token_type=bearer`·`read:user` scope를 요구한다. AES-GCM 저장과 UTC 만료 계산, 비만료·불완전 응답 거부를 검증한다 |
| GitHub token 갱신 | 요청 시 access 만료 60초 전부터 갱신한다. 실제 PostgreSQL에서 동시 refresh·callback 경합, 최신 pair 재확인, 교체 전 token의 늦은 401 보호를 검증한다 |
| GitHub 오류·연결 상태 | 만료된 refresh와 유효한 access 조합은 access를 계속 사용한다. access까지 만료돼 갱신할 수 없거나 refresh가 거부된 경우와 현재 access의 API 401은 revoked commit 후 `token_invalid`다. 네트워크·429·5xx·잘못된 응답은 폐기 없는 503이다. `/api/me`는 access/refresh 만료 조합과 기존 비만료 token을 DB만으로 판정하고 DEVON session은 유지한다 |
| Wanted | Sprint 1은 Wanted-only이며 unsupported site를 차단한다 |
| 면접 | 9턴, 첫 hr_manager 질문, persona target distribution, 텍스트 WS를 검증한다 |
| Evidence | `question_basis`와 `evaluation_basis`, `answer_vs_code` conflict 생성을 검증한다 |
| Refresh | 실제 PostgreSQL에서 rotation·동시 갱신·replay 폐기 commit·옛 generation 보호·logout 경합을 검증한다. Redis 접근 없이 갱신·로그아웃이 동작하고 DB 장애는 503으로 구분한다 |
| 인증 migration·정리 | `0002`의 기존 계정 보존·generation backfill·FK/INDEX, 이전 Redis token 거부, downgrade 범위와 만료 row만 정리하는 반복 실행을 검증한다 |
| GitHub token migration | `0003`은 기존 계정·암호화 token·DEVON session을 보존하고 신규 세 필드의 all-NULL/all-present CHECK를 검증한다. downgrade는 만료형 계정을 revoked로 표시하고 필드를 제거하며 비만료 token 복원을 주장하지 않는다 |
| Redis | 면접 context snapshot 유실 시 Postgres에서 재구성한다. OAuth state는 재구성하지 않고 로그인 절차를 다시 시작하며, Redis 유실·장애가 기존 Refresh DB 기록을 폐기하지 않는다 |
| 리포트 | lazy generation 200/202/409, feedback disagreement unique를 검증한다 |
| 이벤트 | 고정 10개 이벤트 외 값은 거부한다 |

## 테스트 원칙

- GitHub, Wanted, LLM은 mock한다.
- GitHub 원격 rotation과 DB commit 사이 장애에는 재로그인이 필요할 수 있다. 동시성 테스트를 원격·로컬 전체의 원자성이나 정확히 한 번의 실행 보장으로 해석하지 않는다.
- GitHub API 서비스 검증은 후속 저장소 수집·분석 pipeline·worker 검증과 구분한다. `/api/me` 조회나 cron으로 GitHub 갱신을 실행하지 않는다.
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
