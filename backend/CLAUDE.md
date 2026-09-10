# BE 코딩 AI 작업 지침

루트 `CLAUDE.md`를 먼저 따른다. 이 파일은 backend 작업을 맡은 Claude가 읽는 실행 지침이다.

## 읽는 순서

1. `spec/backend/architecture.md`
2. `spec/backend/features/*.md`
3. `spec/backend/verification.md`
4. `spec/shared/contracts/README.md`
5. `spec/shared/contracts/openapi.yaml`
6. `backend/docs/layer-rules.md`
7. 작업 번호에 해당하는 `backend/docs/task-*.md`

`context/*`는 회의 기록이며 직접 구현 기준이 아니다. 충돌이 있으면 `spec/*`와 `backend/docs/*`를 우선하고, `PENDING_FE`, `PENDING_AI`, `PENDING_TEAM` 항목은 임의 구현하지 않는다.

## 고정 구현 기준

- Sprint 1은 텍스트 면접이다. 음성, STT, TTS는 Sprint 2.
- GitHub token은 FE에 노출하지 않는다. BE가 암호화 저장하고 GitHub API를 대행한다.
- GitHub token은 OAuth App long-lived access token 전제다. `github_accounts`에는 `access_token_encrypted`, `token_status`, `token_scope`만 둔다.
- `token_type`, `token_expires_at`, `refresh_token_encrypted`, `refresh_token_expires_at`는 만들지 않는다.
- DEVON 자체 JWT는 사용하되 전달 방식은 `PENDING_FE`.
- DEVON JWT payload에는 GitHub access token을 넣지 않는다.
- API 요청/응답은 camelCase, Python/DB는 snake_case.
- DB enum은 PostgreSQL ENUM이 아니라 `VARCHAR + CHECK`.
- Redis는 ARQ broker, lock, SSE mirror, 면접 context snapshot 같은 짧은 상태에 쓴다. 영구 원본은 Postgres.
- LLM 모델은 Sprint 1에서 `5.5 Luna`로 고정한다. 코드에 모델명을 하드코딩하지 말고 설정/seed에서 읽어 실제 사용값을 DB에 저장한다.
- LLM 구조화 JSON parsing 실패는 자동 1회 재시도 후 실패 처리한다. 깨진 JSON을 downstream에 넘기지 않는다.
- `document_claims`는 Sprint 1에 테이블만 만들고 row 생성/claim 추출은 하지 않는다.
- `evidence_conflicts`는 Sprint 1에 만들며 `answer_vs_code` 용도로만 사용한다. `claim_id` FK는 Sprint 2.
- `report_persona_feedbacks`, `topic_taxonomy`, `interview_personas`, `probe_patterns`, `feedback_signals`, `eval_cases`, `eval_runs`, `auth_sessions`는 Sprint 1 DB에서 제외한다.

## 실행 환경

작업 디렉터리: `backend`

```text
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## 검증 명령

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

DB 기능은 PostgreSQL 기준으로 검증한다. SQLite로 대체하지 않는다. GitHub, Wanted, LLM은 mock fixture를 사용한다.

## 산출물 위치

- 고정 설계: `spec/backend/`
- 공통 API 계약: `spec/shared/contracts/openapi.yaml`
- 구현 체크리스트: `backend/docs/task-*.md`
- 결정/보류 변경 기록: 루트 `report.md`
- AI 실행 계획: `.claude/scratch/plans/`
