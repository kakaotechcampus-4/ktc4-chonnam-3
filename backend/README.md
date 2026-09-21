# Backend

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 (전남대 3팀) BE.

AI 원본은 [ai/src/devon_ai](../ai/src/devon_ai/)의 로컬 Python 패키지로 분리한다. backend의 API·ARQ worker가 같은 프로세스 안에서 import하며 별도 AI 서버는 없다. [승인 설계](../spec/ai/designs/2026-09-12-ai-package-structure.md)와 [AI 개발 안내](../ai/README.md)를 함께 읽는다. 현재 실행 범위는 GitHub 가입·로그인, 인증 갱신·로그아웃, `/api/me`다. AI·분석·대시보드·프로필 API와 worker는 아직 골격이며, 인증 완료가 저장소 수집 완료를 뜻하지 않는다.

위 인증 기능의 실행 진입점은 `app.main:app`이다. 루트 `compose.deploy.yaml`은 별도의
`app.deploy_check:app`으로 `/api/health`만 제공한다. 배포 점검 성공을 인증 앱의 운영 배포 완료로
해석하지 않으며, 전환 전제는 [배포 가이드](docs/deploy.md)를 따른다.

설계 문서는 [`docs/`](docs/) 안에 있다.

| 문서                                      | 내용                                                  |
| ----------------------------------------- | ----------------------------------------------------- |
| [layer-rules.md](docs/layer-rules.md)     | 폴더 경계 · 레이어 규칙 · 금지 목록 · 네이밍 · 직렬화 |
| [db-schema.md](docs/db-schema.md)         | 테이블 목록 · 제약 · 1차/2차 경계 · 미결              |
| [error-reasons.md](docs/error-reasons.md) | 에러 봉투 · 3계층 reason 레지스트리                   |
| [redis-keys.md](docs/redis-keys.md)       | Redis 키 설계표                                       |
| [pipeline.md](docs/pipeline.md)           | ARQ · run 실행 흐름 · SSE · WebSocket                 |
| [testing.md](docs/testing.md)             | 테스트 전략 · 필수 테스트 4개 · Eval                  |
| [deploy.md](docs/deploy.md)               | EC2 배포 점검 · 인증 운영 전제 · 쿠키 · CI            |
| [api-spec.md](docs/api-spec.md)           | FE 계약 링크 + 합의된 변경                            |

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

GitHub scope는 `read:user`만 사용한다. OAuth App의 만료형 access/refresh token을 사용하며, 새 로그인 응답에는 `access_token`, `expires_in`, `refresh_token`, `refresh_token_expires_in`, `token_type=bearer`와 유효한 `read:user` scope가 필요하다. `token_type`은 응답 검증에만 사용하고 DB 컬럼은 두지 않는다. local callback은 Vite의 `/api` proxy를 거쳐 backend `localhost:8000`으로 전달되므로 frontend dev server와 backend를 함께 실행한다. 포트를 변경하면 OAuth App 등록값과 두 환경값도 함께 변경한다.

GitHub의 **Settings → Developer settings → OAuth Apps → 해당 앱 → Optional features**에서 만료형 access token 옵션을 활성화한다. 앱 전체에 이 설정을 적용하므로 `offline_access` scope는 추가하지 않는다. 응답 TTL로 UTC 만료 시각을 저장하고, BE의 GitHub API 호출 시 access 만료까지 60초 이하이면 refresh token으로 새 pair를 받아 암호화 저장한다. 토큰 응답·갱신 규칙은 [GitHub 공식 안내](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)를 따른다. 이는 DEVON JWT의 Access 15분·Refresh 14일 정책과는 별개다.

GitHub에서 동의한 뒤 서비스로 돌아와 `provider_unavailable`이 표시되면 앱의 토큰 만료 옵션과 응답 형식을 확인한다. 토큰 교환이 HTTP 200이어도 필수 token pair·TTL·type·scope가 누락되거나 잘못되면 저장하지 않는다. 진단 시에는 HTTP 상태·오류 분류·필드 존재 여부만 기록한다. token, code, state, cookie 또는 응답 본문 전체를 출력하지 않는다.

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

### GitHub 만료형 토큰 전환

서버를 중지하고 진행 중인 인증·GitHub 요청을 종료한 뒤 `uv run alembic upgrade head`로 `0003`까지 적용하고 새 서버를 시작한다. `0003`은 GitHub access 만료 시각, 암호화 refresh token, refresh 만료 시각을 추가한다. 기존 계정과 비만료 access token은 세 필드가 모두 NULL인 상태로 보존하며, 해당 사용자가 다음 GitHub 로그인을 완료하면 만료형 pair로 교체한다. DEVON의 기존 JWT와 `auth_sessions`는 이 migration으로 변경하지 않는다.

현재 서버는 후속 GitHub API용 `app.state.github.get(user_id, path)`와 요청 시 갱신을 제공한다. `/api/me`는 DB만 읽어 GitHub 연결 상태를 계산하며 갱신을 실행하지 않는다. 저장소 수집 API·pipeline·worker는 아직 골격이고, 새 공개 경로나 GitHub 갱신 cron은 추가하지 않는다.

GitHub refresh token이 만료돼도 access가 아직 유효하면 남은 수명 동안 사용한다. access까지 만료돼 갱신할 수 없거나 GitHub가 refresh를 거부하면 연결을 `revoked`로 기록하고 `token_invalid`를 반환한다. 사용자는 GitHub 로그인 절차를 다시 진행해야 한다. 현재 access token의 API 401도 같은 방식으로 처리하되, 교체 전 token에서 늦게 도착한 401이 새 pair를 폐기하지 않게 확인한다. 네트워크·429·5xx·잘못된 응답은 기존 pair를 폐기하지 않고 `provider_unavailable`로 처리한다. GitHub의 원격 token 교체와 DB commit은 하나의 원자적 트랜잭션이 아니므로 그 사이 장애가 발생하면 재로그인이 필요할 수 있다.

`0003` downgrade는 만료형 계정을 `revoked`로 표시하고 추가한 세 필드를 제거한다. 비만료 token으로 되돌려 주지 않으므로, 되돌린 서버가 지원하는 GitHub 앱 설정과 재로그인 절차도 함께 준비해야 한다. 상세 결정은 [GitHub OAuth와 DEVON 세션](../spec/shared/decisions/0002-github-oauth.md)을 따른다.

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

API 표면의 원본은 [`spec/shared/contracts/openapi.yaml`](../spec/shared/contracts/openapi.yaml) 이다.
WebSocket · SSE 메시지와 브라우저 이동 흐름은
[`frontend/docs/api-spec.md`](../frontend/docs/api-spec.md) 를 함께 따른다
(범위는 [`spec/shared/contracts/README.md`](../spec/shared/contracts/README.md) 참고).
응답 타입은 [`frontend/src/types/api.ts`](../frontend/src/types/api.ts)와 맞춘다. 이관 상태는
[`spec/shared/contracts/migration.md`](../spec/shared/contracts/migration.md)를 따른다.
`tests/contract/`와 공통 계약 검사는 구현된 범위만 검증하며 전체 서비스 검증을 뜻하지 않는다.

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
