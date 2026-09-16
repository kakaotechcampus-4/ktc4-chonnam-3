# Backend

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 (전남대 3팀) BE.

AI 원본은 [ai/src/devon_ai](../ai/src/devon_ai/)의 로컬 Python 패키지로 분리한다. backend의 API·ARQ worker가 같은 프로세스 안에서 import하며 별도 AI 서버는 없다. [승인 설계](../spec/ai/designs/2026-09-12-ai-package-structure.md)와 [AI 개발 안내](../ai/README.md)를 함께 읽는다. 현재 실행 범위는 GitHub 가입·로그인, 인증 갱신·로그아웃, `/api/me`다. AI·분석·대시보드·프로필 API와 worker는 아직 골격이며, 인증 완료가 저장소 수집 완료를 뜻하지 않는다.

설계 문서는 [`docs/`](docs/) 안에 있다.

| 문서 | 내용 |
| --- | --- |
| [layer-rules.md](docs/layer-rules.md) | 폴더 경계 · 레이어 규칙 · 금지 목록 · 네이밍 · 직렬화 |
| [db-schema.md](docs/db-schema.md) | 테이블 목록 · 제약 · 1차/2차 경계 · 미결 |
| [error-reasons.md](docs/error-reasons.md) | 에러 봉투 · 3계층 reason 레지스트리 |
| [redis-keys.md](docs/redis-keys.md) | Redis 키 설계표 |
| [pipeline.md](docs/pipeline.md) | ARQ · run 실행 흐름 · SSE · WebSocket |
| [testing.md](docs/testing.md) | 테스트 전략 · 필수 테스트 4개 · Eval |
| [deploy.md](docs/deploy.md) | DuckDNS · Caddy · 쿠키 · CI |
| [api-spec.md](docs/api-spec.md) | FE 계약 링크 + 합의된 변경 |

## 기술 스택

- FastAPI + Python 3.12
- PostgreSQL 15 (asyncpg + SQLAlchemy 2.0 async, Alembic)
- Redis 7 (OAuth state; 락 · SSE pub/sub는 후속 구현)
- ARQ (비동기 큐)
- uv (의존성) / ruff · mypy / pytest

## 시작하기

`backend/`만 따로 복사하지 않고 형제 `ai/`를 포함한 저장소에서 작업한다. `uv sync --locked --python 3.12`는 `../ai`를 로컬 editable 의존성으로 설치한다. AI의 의존성·metadata 변경 시 두 프로젝트의 lock을 확인한다. Docker build context도 저장소 루트를 사용하며, 이미지 내부에는 `/srv/backend`와 `/srv/ai` 형제 경로를 유지한다.

```bash
git clone <repo-url>
cd ktc4-chonnam-3/backend
cp .env.example .env      # 값 채우기
docker compose up -d db redis
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/api`가 API prefix다. 인증에는 seed나 worker 실행이 필요하지 않다. frontend에서는 `npm ci` 후 `npm run dev`로 `http://localhost:5173`을 연다.

### 로컬 GitHub OAuth App

GitHub Settings의 OAuth Apps에서 개발용 App을 만들고 다음 값을 등록한다.

| 항목 | 값 |
| --- | --- |
| Homepage URL | `http://localhost:5173` |
| Authorization callback URL | `http://localhost:5173/api/auth/github/callback` |

발급된 Client ID/secret을 `.env`의 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`에 넣고 아래 값을 맞춘다.

```dotenv
APP_ENV=local
FRONTEND_ORIGIN=http://localhost:5173
GITHUB_REDIRECT_URI=http://localhost:5173/api/auth/github/callback
JWT_ISSUER=devon
JWT_AUDIENCE=devon-api
```

GitHub scope는 `read:user`만 사용한다. OAuth App은 비만료 access token 설정을 사용하며, `expires_in`, `refresh_token`, `refresh_token_expires_in`이 포함된 응답은 저장하지 않고 login을 실패시킨다. local callback은 Vite의 `/api` proxy를 거쳐 backend `localhost:8000`으로 전달되므로 frontend dev server와 backend를 함께 실행한다. 포트를 변경하면 OAuth App 등록값과 두 환경값도 함께 변경한다.

GitHub의 **Settings → Developer settings → OAuth Apps → 해당 앱 → Optional features**에서 만료형 access token 옵션이 활성화되어 있지 않은지 확인한다. 이 프로젝트는 GitHub 토큰의 자동 갱신을 구현하지 않았으므로 해당 옵션을 해제한 뒤 새 로그인 절차를 시작해야 한다. 설정 위치는 [GitHub 공식 안내](https://docs.github.com/en/apps/oauth-apps/maintaining-oauth-apps/activating-optional-features-for-oauth-apps)를 따른다. 이는 DEVON JWT의 Access 15분·Refresh 14일 정책과는 별개다.

GitHub에서 동의한 뒤 서비스로 돌아와 `provider_unavailable`이 표시되면 실제 네트워크 장애로 단정하지 않는다. 토큰 교환이 HTTP 200이어도 응답에 위 만료·갱신 필드가 있으면 현재 계약상 거부한다. 먼저 앱의 토큰 만료 옵션을 확인하고, 진단 시에는 HTTP 상태·오류 분류·필드 존재 여부만 기록한다. token, code, state, cookie 또는 응답 본문 전체를 출력하지 않는다.

local/dev에서는 GitHub Client ID와 secret이 둘 다 비어 있을 때만 auth 외 개발을 위해 서버를 시작할 수 있고 login은 503으로 실패한다. 둘 중 하나만 설정하면 구성 오류이며, prod에서는 둘 다 필수다.

JWT signing key와 AES-256 key는 서로 다른 값으로 생성해 `JWT_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`에 넣는다. 출력값을 저장소에 commit하지 않는다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 인증 테스트

GitHub HTTP만 mock하고 PostgreSQL·Redis는 실제 독립 테스트 저장소를 사용한다. 아래 두 환경값이 없으면 통합 테스트는 건너뛰므로 일반 `pytest` 통과만으로 인증 통합 검증을 주장하지 않는다.

```bash
docker compose exec db createdb -U devon devon_oauth_test
TEST_DATABASE_URL=postgresql+asyncpg://devon:devon@localhost:5432/devon_oauth_test \
TEST_REDIS_URL=redis://localhost:6379/15 uv run pytest
```

PowerShell에서는 같은 값을 `$env:TEST_DATABASE_URL`, `$env:TEST_REDIS_URL`에 설정한 후 `uv run pytest`를 실행한다. 테스트는 해당 DB의 인증 테이블을 삭제·재생성하고 Redis DB 15를 비우므로 실제 개발·운영 데이터를 가리키면 안 된다. 실제 GitHub 로그인은 OAuth App 비밀값을 `.env`에 입력한 뒤 브라우저에서 별도로 확인한다.

### Refresh 저장소 전환

JWT·쿠키·FE 흐름은 유지하며 Refresh 유효·폐기 기록만 PostgreSQL의 `users.refresh_generation`과 `auth_sessions`에서 관리한다. migration `0002`는 기존 사용자와 GitHub 계정을 보존한다. raw JWT나 Redis Refresh 기록은 저장하지 않는다. Redis가 내려가도 기존 로그인 갱신·로그아웃은 DB로 처리하지만 새 GitHub 로그인은 OAuth state 때문에 Redis가 필요하다.

기존 Redis 방식의 인증 인스턴스를 먼저 중지하고 진행 중인 요청을 종료한 뒤 `uv run alembic upgrade head`를 실행하고 새 버전만 시작한다. 두 저장소를 원본으로 쓰는 구버전·신버전을 동시에 운영하지 않는다. 이전 Redis Refresh는 가져오지 않으므로 기존 로그인은 Access 만료 후 재로그인이 필요하다. 이전 키는 TTL로 자연 만료시키며, downgrade도 재로그인이 필요하고 옛 Redis 기록을 다시 활성화하지 않는다.

만료 기록은 backend 디렉터리에서 다음 명령으로 정리한다.

```bash
uv run python -m scripts.cleanup_auth_sessions
```

Alembic과 정리 명령은 `core/config.py`의 DB 전용 설정(`DATABASE_URL`, `.env` 또는 환경 변수)을 사용한다. GitHub secret·JWT signing key·암호화 키·Redis 연결이 필요하지 않다. 정리는 `expires_at <= 현재 UTC`인 row만 삭제하고 삭제 개수만 출력한다. 별도 스케줄러를 설치하거나 API마다 작업을 띄우지 않고 기존 배포 스케줄러에 주기 실행을 등록한다. 시간별 실행 예시와 되돌리기 주의사항은 [배포 가이드](docs/deploy.md#10-refresh-저장소-전환과-정리)를 따른다.

## 스크립트

| 명령                                                  | 설명              |
| ----------------------------------------------------- | ----------------- |
| `docker compose up -d db redis`                       | DB·Redis만 띄우기 |
| `uv sync`                                             | 의존성 설치       |
| `uv run alembic upgrade head`                         | 마이그레이션      |
| `uv run python -m scripts.cleanup_auth_sessions`     | 만료 Refresh 기록 정리 |
| `uv run python -m scripts.seed_all`                   | 도메인 지식 시드  |
| `uv run uvicorn app.main:app --reload --port 8000`    | API               |
| `uv run arq app.workers.arq_app.WorkerSettings`       | 워커              |
| `uv run ruff check . && uv run ruff format --check .` | 린트              |
| `uv run mypy app`                                     | 타입 체크         |
| `uv run pytest`                                       | 테스트            |

## 폴더 구조

```
app/
├─ main.py          # FastAPI 인스턴스, 라우터 등록, 예외 핸들러, lifespan
├─ core/            # 설정·에러·로깅·보안·토큰암복호화·의존성
├─ db/              # engine/session + models/ (테이블별 모듈)
├─ shared/          # CamelModel, enums, 페이지네이션, clock
├─ features/        # 도메인별 API (auth, me, analysis, interview, report) — FE src/features 와 1:1
│  └─ analysis/pipeline/   # job_type 3종 + steps/ 7개
├─ agents/          # AI 패키지 연결 예정 경계. Director 원본은 ../ai/src/devon_ai
│  └─ director/     # agent.py + 실제 Evidence 도구 adapter 경계
├─ llm_tasks/       # AI task 연결, prompt_loader, BE 규칙 변환·집계
├─ integrations/    # 외부 I/O (github, llm, jd, extract). DB 를 모른다
├─ realtime/        # Redis pub/sub, SSE, WS 레지스트리
└─ workers/         # ARQ WorkerSettings + tasks (얇은 껍데기)

docs/               # db-schema, error-reasons, redis-keys, task-01~17
migrations/         # Alembic
scripts/            # 도메인 지식 시드 · 만료 인증 기록 정리
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
- **Agent는 Director 하나다.** AI 원본은 `devon_ai.agents.director`이며 Evidence 조회는 별도 Agent가 아니라 주입된 Tool이다. AI의 repo shallow/deep·답변 분석·리포트 모듈은 `devon_ai.llm_tasks`에 둔다. Sprint 1 Wanted 변환·프로필 확정 집계는 BE에서 LLM 없이 처리하며 문서 Claim은 후속이다.
- `llm_tasks/prompt_loader.py` 만 `AsyncSession` 을 받는다. service 가 이걸로 프롬프트를 로드해
  문자열로 주입하므로, `agents/` 와 나머지 task 는 DB 를 모른 채 Eval 에서 단독 실행된다.
- `integrations/speech/` 는 없다 — 스프린트1 은 양방향 텍스트다 (스프린트2 에 STT/TTS 추가).

## API 스펙

API 표면의 유일한 진실은 [`spec/shared/contracts/openapi.yaml`](../spec/shared/contracts/openapi.yaml)이고,
응답 타입은 [`frontend/src/types/api.ts`](../frontend/src/types/api.ts)와 맞춘다. 이관 상태는
[`spec/shared/contracts/migration.md`](../spec/shared/contracts/migration.md)를 따른다.

- 에러 봉투와 reason 목록 → [`docs/error-reasons.md`](docs/error-reasons.md)
- Redis 키 → [`docs/redis-keys.md`](docs/redis-keys.md)
- 스키마 결정과 1차/2차 경계 → [`docs/db-schema.md`](docs/db-schema.md)
- 스펙 ↔ 데이터모델 충돌 결정 → [`docs/db-schema.md`](docs/db-schema.md) "설계 초기안 대비 변경"

**FE 와 합의된 변경 (BE 내부명을 그대로 쓴다 — 경계 매핑 레이어 없음)**

| `types/api.ts` 현재                                           | 확정                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------------ |
| `AgentRole = tech_lead \| senior_developer \| manager`        | `tech_lead` / `hr_manager` / `domain_lead`                   |
| `StepKey` 4개                                                 | 7개 (`doc_extract` … `match_score`)                          |
| `jd_unreachable` / `jd_parse_failed` / `github_token_expired` | `jd_fetch_failed` / `jd_extraction_failed` / `token_invalid` |
| WS 오디오 바이너리 + `transcript`                             | 스프린트1 은 텍스트, 스프린트2 에 STT/TTS                    |

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- 브랜치명 예: `feature/be-xxx`, `fix/be-xxx`.
