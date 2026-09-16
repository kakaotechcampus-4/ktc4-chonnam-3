# task-01 — 프로젝트 셋업

> 선행: 없음
> 근거: `spec/backend/architecture.md`, `backend/docs/layer-rules.md`

## 목표

FastAPI backend 기본 실행, 설정, 헬스체크, lint/type/test 명령을 준비한다.

## 작업

- `pyproject.toml`에 FastAPI, SQLAlchemy async, asyncpg, Alembic, Redis/ARQ, httpx, Pydantic 설정을 확인한다.
- `app/main.py`에 `/health` 200 응답을 둔다.
- `app/core/config.py`에서 모든 환경변수를 단일 진입점으로 읽는다.
- `.env.example`에 DB, Redis, GitHub OAuth, DEVON JWT, 암호화 키, LLM 모델 `5.5 Luna`, 문서 크기 10MB, 면접 9턴/1200초 기본값을 둔다.
- STT/TTS 설정은 Sprint 2 주석으로만 남긴다.
- Docker compose는 Postgres와 Redis를 제공한다.

## 완료 조건

- `uv sync`가 성공한다.
- `/health`가 200을 반환한다.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`, `uv run pytest` 실행 결과를 보고한다.
