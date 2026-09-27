# task-01 — 프로젝트 셋업

> 선행: 없음
> 근거: `spec/backend/architecture.md`, `backend/docs/layer-rules.md`

## 목표

FastAPI backend 기본 실행, 설정, 헬스체크, lint/type/test 명령을 준비한다.

## 작업

- `pyproject.toml`에 FastAPI, SQLAlchemy async, asyncpg, Alembic, Redis/ARQ, httpx, Pydantic 설정을 확인한다.
- `app/main.py`에 `/health` 200 응답을 둔다.
- `app/core/config.py`에서 모든 환경변수를 단일 진입점으로 읽는다.
- `.env.example`에 DB, Redis, GitHub OAuth, DEVON 세션(`SESSION_COOKIE_NAME=devon_session`, `SESSION_TTL_SECONDS=1209600`), 암호화 키, OpenAI 인증 변수 `OPENAI_API_KEY`(빈 값)와 `LLM_DEFAULT_MODEL=gpt-5.6-luna`, 포트폴리오 크기 20MB, JD 재사용 7일, 면접 9턴/1200초 기본값을 둔다.
- 세션 쿠키는 HttpOnly·`Path=/`·`SameSite=Lax`와 운영 환경 `Secure`를 사용한다. 14일 sliding 세션 연결은 task-06에서 구현·검증하며 DEVON JWT·refresh 설정은 Sprint 2로 넘긴다.
- 공급자·모델은 [0011 결정](../../spec/ai/decisions/0011-sprint1-model-selection.md)을 따른다. 예시 변수의 config·seed·client 연결과 실제 모델 접근은 구현·검증하며, 기존 `anthropic` 의존성을 현재 공급자 선택이나 연결 완료의 근거로 삼지 않는다. SDK 의존성 정리는 실제 client 연결 작업에서 함께 처리한다.
- STT/TTS 설정은 Sprint 2 주석으로만 남긴다.
- Docker compose는 Postgres와 Redis를 제공한다.

## 완료 조건

- `uv sync`가 성공한다.
- `/health`가 200을 반환한다.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`, `uv run pytest` 실행 결과를 보고한다.
