# Backend

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 (전남대 3팀) BE.

AI 원본은 [ai/src/devon_ai](../ai/src/devon_ai/)의 로컬 Python 패키지로 분리한다. backend의 API·ARQ worker가 같은 프로세스 안에서 import하며 별도 AI 서버는 없다. [승인 설계](../spec/ai/designs/2026-09-12-ai-package-structure.md)와 [AI 개발 안내](../ai/README.md)를 함께 읽는다.

현재 구현 범위는 GitHub OAuth 로그인·재연동, Redis 세션 인증, `/me` 계열 조회와 public 저장소 목록의 초기 수집이다. #41의 DB 모델·초기 migration을 가져왔으며 AI 분석·면접·리포트 생성의 실행 연결까지 완료한 것은 아니다.

설계 문서는 [`docs/`](docs/) 안에 있다.

| 문서                                      | 내용                                                  |
| ----------------------------------------- | ----------------------------------------------------- |
| [layer-rules.md](docs/layer-rules.md)     | 폴더 경계 · 레이어 규칙 · 금지 목록 · 네이밍 · 직렬화 |
| [db-schema.md](docs/db-schema.md)         | 테이블 목록 · 제약 · 1차/2차 경계 · 미결              |
| [error-reasons.md](docs/error-reasons.md) | 에러 봉투 · 3계층 reason 레지스트리                   |
| [redis-keys.md](docs/redis-keys.md)       | Redis 키 설계표                                       |
| [pipeline.md](docs/pipeline.md)           | ARQ · run 실행 흐름 · SSE · WebSocket                 |
| [testing.md](docs/testing.md)             | 테스트 전략 · 구현 시 검증할 항목 · Eval              |
| [deploy.md](docs/deploy.md)               | AWS 통합 배포(CloudFront) · 쿠키 · CI                 |
| [api-spec.md](docs/api-spec.md)           | FE 계약 링크 + 합의된 변경                            |
| [local-oauth.md](docs/local-oauth.md)     | 실제 GitHub 로그인 설정 · API/worker/FE 실행 · 격리 테스트 |

## 기술 스택

- FastAPI + Python 3.12
- PostgreSQL 15 (asyncpg + SQLAlchemy 2.0 async, Alembic)
- Redis 7 (세션 · 락 · SSE pub/sub)
- ARQ (비동기 큐)
- uv (의존성) / ruff · mypy / pytest

## 시작하기

`backend/`만 따로 복사하지 않고 형제 `ai/`를 포함한 저장소에서 작업한다. `uv sync --locked --python 3.12`는 `../ai`를 로컬 editable 의존성으로 설치한다. AI의 의존성·metadata 변경 시 두 프로젝트의 lock을 확인한다. Docker build context도 저장소 루트를 사용하며, 이미지 내부에는 `/srv/backend`와 `/srv/ai` 형제 경로를 유지한다.

먼저 [로컬 OAuth 안내](docs/local-oauth.md)에 따라 새 개발 DB, GitHub OAuth App과 `.env`를 준비한다. 기존 DB는 `alembic current`와 migration 이력을 검토한 후 진행한다. 현재 개발 환경의 ignored PostgreSQL(55432)에는 이전 `0002`·`0003` 계열 이력이 있을 수 있으므로 그대로 upgrade하거나 데이터를 삭제하지 않는다.

`backend/`에서 API를 실행한다.

```text
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000 --no-access-log
```

별도 터미널에서 `uv run arq app.workers.arq_app.WorkerSettings`를 실행한다. `frontend/.env.local`에는 `VITE_USE_MSW=false`를 설정하고 `frontend/`에서 `npm ci`, `npm run dev`를 실행한다. 브라우저는 `http://localhost:5173`으로 접속한다. OAuth App에 등록할 콜백은 로그인·재연동 공통 `http://localhost:5173/auth/github/callback` 하나다. Vite가 내부 `/api/auth/github/callback`으로 전달하며 코드 교환의 `redirect_uri`도 공개 주소를 유지한다.

로그인·재연동 요청 scope는 `read:user`뿐이다. OAuth App의 **Expire user access tokens는 OFF**로 유지하고 `offline_access`를 요청하지 않는다. DEVON 세션은 Redis에 14일 sliding으로 저장하고 GitHub 장기 토큰은 별도로 AES-GCM 암호화해 PostgreSQL에 저장한다.

## 스크립트

| 명령                                                  | 설명              |
| ----------------------------------------------------- | ----------------- |
| `docker compose up -d db redis`                       | DB·Redis만 띄우기 |
| `uv sync`                                             | 의존성 설치       |
| `uv run alembic upgrade head`                         | 마이그레이션      |
| `uv run python -m scripts.seed_all`                   | 도메인 지식 시드 경계 — 로그인 실행에 불필요 |
| `uv run uvicorn app.main:app --reload --port 8000 --no-access-log` | API — OAuth query 로그 제외 |
| `uv run arq app.workers.arq_app.WorkerSettings`       | 워커              |
| `uv run ruff check . && uv run ruff format --check .` | 린트              |
| `uv run mypy app`                                     | 타입 체크         |
| `uv run pytest`                                       | 테스트 — 격리 `TEST_DATABASE_URL`·`TEST_REDIS_URL` 필요 |

통합 테스트는 PostgreSQL DB 이름에 `_test`가 포함되어야 하며 Redis DB는 13·14·15 중 테스트 전용 번호를 명시해야 한다. fixture가 해당 DB 테이블과 Redis DB를 비우므로 개발·운영 데이터를 지정하지 않는다. 환경변수가 없으면 관련 통합 테스트는 skip된다. 자세한 명령은 [검증 절차](docs/local-oauth.md#검증)를 따른다.

## 폴더 구조

```
app/
├─ main.py          # FastAPI 인스턴스, 라우터 등록, 예외 핸들러, lifespan
├─ core/            # 설정·에러·로깅·보안·토큰암복호화·의존성
├─ db/              # engine/session + models/ (테이블별 모듈)
├─ shared/          # CamelModel, enums, 페이지네이션, clock
├─ features/        # 도메인별 API (auth, me, analysis, interview, report) — FE src/features 와 1:1
│  └─ analysis/pipeline/   # 분석 7단계 골격. 현행 job 연결은 docs/pipeline.md 기준
├─ agents/          # AI 패키지 연결 예정 경계. Director 원본은 ../ai/src/devon_ai
│  └─ director/     # agent.py + 실제 Evidence 도구 adapter 경계
├─ llm_tasks/       # AI task 연결, prompt_loader, BE 규칙 변환·집계
├─ integrations/    # 외부 I/O (github, llm, jd, extract). DB 를 모른다
├─ realtime/        # Redis pub/sub, SSE, WS 레지스트리
└─ workers/         # ARQ WorkerSettings + tasks (얇은 껍데기)

docs/               # db-schema, error-reasons, redis-keys, task-01~17
migrations/         # Alembic
scripts/            # 도메인 지식 시드
tests/              # 공개 계약 / features / agents(BE 설치 연결) / llm_tasks
```

AI 자체 모듈·구조 테스트는 `../ai/src/devon_ai/`와 `../ai/tests/`에 있다. BE 연결 검사는 `uv run --locked pytest tests/agents/test_ai_package_imports.py`로 실행한다. 이 smoke test는 설치와 import만 검사하며 service 호출·모델 결과·DB 저장을 증명하지 않는다.

호출 방향은 한 방향이다.

```
router → service → { queries | agents | llm_tasks | integrations | realtime }
```

- `router.py` — 요청 검증·응답 직렬화만. 비즈니스 로직·DB 직접 접근 금지.
- `service.py` — 트랜잭션 경계. 여기서만 `commit()`.
- 읽기 쿼리 모음은 **`queries.py`** 다. `repository.py` 라는 이름은 쓰지 않는다 —
  `repositories` 가 GitHub 레포 테이블이라 이름이 겹친다.
- **Agent는 Director 하나다.** AI 원본은 `devon_ai.agents.director`이며 Evidence 조회는 별도 Agent가 아니라 주입된 Tool이다. AI의 repo shallow/deep·답변 분석·리포트 모듈은 `devon_ai.llm_tasks`에 둔다. Sprint 1 Wanted 변환·프로필 언어·유형 집계는 BE에서 LLM 없이 처리하며, 개인 역할 요약만 [0019 결정](../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 기존 `profile_summary` 경계에서 LLM으로 생성할 구현 대상이다. 문서 Claim은 Sprint 2다.
- `llm_tasks/prompt_loader.py` 만 `AsyncSession` 을 받는다. service 가 이걸로 프롬프트를 로드해
  문자열로 주입하므로, `agents/` 와 나머지 task 는 DB 를 모른 채 Eval 에서 단독 실행된다.
- `integrations/speech/` 는 없다 — 스프린트1 은 양방향 텍스트다 (스프린트2 에 STT/TTS 추가).

## API 스펙

API 표면의 원본은 [`spec/shared/contracts/openapi.yaml`](../spec/shared/contracts/openapi.yaml) 이다.
WebSocket · SSE · 브라우저 이동 경로는 OpenAPI 로 표현할 수 없어
[`frontend/docs/api-spec.md`](../frontend/docs/api-spec.md) 가 원본이다
(범위는 [`spec/shared/contracts/README.md`](../spec/shared/contracts/README.md) 참고).
응답 필드·enum은 OpenAPI를 기준으로 구현하고 [`frontend/src/types/api.ts`](../frontend/src/types/api.ts)도 이에 맞춘다.
`tests/contract/`는 현재 자리만 마련되어 있으며 응답 키 집합·required/nullable/enum을 대조하는 테스트는 구현 대기다.

- 에러 봉투와 reason 목록 → [`docs/error-reasons.md`](docs/error-reasons.md)
- Redis 키 → [`docs/redis-keys.md`](docs/redis-keys.md)
- 스키마 결정과 1차/2차 경계 → [`docs/db-schema.md`](docs/db-schema.md)
- 스펙 ↔ 데이터모델 충돌 결정 → [`docs/db-schema.md`](docs/db-schema.md) "설계 초기안 대비 변경"

**합의된 API 표기 (옛 표기와 비교)**

| 옛 표기                                                      | 현행 계약                                                    |
| ------------------------------------------------------------- | ------------------------------------------------------------ |
| `AgentRole = tech_lead \| senior_developer \| manager`        | `tech_lead` / `hr_manager` / `domain_lead`                   |
| `StepKey` 4개                                                 | 7개 (`doc_extract` … `match_score`)                          |
| `jd_unreachable` / `jd_parse_failed` / `github_token_expired` | `jd_fetch_failed` / `jd_extraction_failed` / `token_invalid` |
| WS 오디오 바이너리 + `transcript`                             | 스프린트1 은 텍스트, 스프린트2 에 STT/TTS                    |

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- 브랜치명 예: `feature/be-xxx`, `fix/be-xxx`.
