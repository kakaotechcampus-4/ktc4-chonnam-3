# 로컬 GitHub 로그인 실행

현재 범위는 OAuth 로그인·재연동, Redis 세션, `/me`·홈·프로필·면접 이력 조회와 public 저장소 목록 수집이다. 저장소 코드를 분석하거나 AI 면접·리포트를 생성하는 작업은 이 실행 안내의 범위가 아니다.

## GitHub OAuth App

GitHub의 OAuth App을 사용한다. 로컬 Home URL은 `http://localhost:5173`, **Authorization callback URL은 `http://localhost:5173/auth/github/callback` 하나**로 설정한다. 로그인과 재연동이 같은 callback을 사용하며 서버에 저장한 state의 purpose로 흐름을 구분한다. `/auth/github/link/callback`은 이전 경로 호환용이며 새 등록 주소가 아니다.

로그인·재연동 모두 `read:user`만 요청한다. public 저장소 목록에는 `repo`·`public_repo`가 필요하지 않다. OAuth App의 **Expire user access tokens는 OFF**로 두고 `offline_access`를 추가하지 않는다. 만료·refresh 필드가 포함된 토큰 응답은 현재 long-lived 저장 모델과 맞지 않아 `502 provider_unavailable`로 거부한다. [GitHub 공식 OAuth 안내](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)를 참고한다.

이 설정 불일치는 `GitHub 로그인 설정이 서비스와 맞지 않습니다. 관리자에게 문의해주세요.` 메시지와 서버의 `github_oauth_token_mode_unsupported` 이벤트로 구분한다. 토큰 원문은 로그에 기록하지 않는다. GitHub의 Settings → Developer settings → OAuth Apps에서 사용 중인 앱의 옵션을 끄고 저장한 뒤 `/login`에서 새 로그인 요청을 시작한다. 이미 소비한 callback URL을 새로고침하지 않는다.

## DB와 환경변수 준비

저장소의 `backend/`와 형제 `ai/`가 모두 필요하다. `backend/`에서 `uv sync --locked`를 실행한다. `.env`가 없을 때만 `.env.example`을 복사하고 기존 자격 증명은 보존한다.

```text
uv sync --locked
docker compose up -d db redis
docker compose exec db createdb -U devon devon_session_local
```

위 `createdb`는 새로운 로컬 개발 DB를 만드는 예시다. 이미 DB가 있으면 같은 이름으로 다시 만들지 말고 먼저 이력을 확인한다. `.env`에는 다음 값을 설정한다. 아래 비밀값 표시는 실제 값으로 채우며 파일을 커밋하지 않는다.

```dotenv
APP_ENV=local
API_PREFIX=/api
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_URL=postgresql+asyncpg://devon:devon@localhost:5432/devon_session_local
REDIS_URL=redis://localhost:6379/0
SESSION_COOKIE_NAME=devon_session
SESSION_TTL_SECONDS=1209600
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
GITHUB_CLIENT_ID=<OAuth App client ID>
GITHUB_CLIENT_SECRET=<OAuth App client secret>
GITHUB_LOGIN_SCOPE=read:user
GITHUB_LINK_SCOPE=read:user
GITHUB_REDIRECT_URI=http://localhost:5173/auth/github/callback
TOKEN_ENCRYPTION_KEY=<base64로 인코딩한 랜덤 32바이트 키>
```

암호화 키는 로컬에서 `uv run python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"`로 생성해 `.env`에 저장할 수 있다. 저장된 토큰을 복호화하려면 같은 키가 필요하다. 토큰·쿠키·OAuth code와 키를 공유 로그에 남기지 않는다.

**기존 DB migration은 별도 확인이 필요하다.** 이 브랜치는 #41의 초기 스키마를 사용한다. 현재 개발 환경의 ignored PostgreSQL 55432에는 이전 OAuth용 `0002`·`0003` migration 이력이 있을 수 있다. 그 DB에 현재 migration을 바로 적용하거나 drop/stamp로 맞추지 않는다. 새 DB로 실행하거나 `uv run alembic current`, `uv run alembic history`와 기존 스키마를 비교한 뒤 데이터 보존 전환을 검토한다.

위 `.env`가 새 개발 DB를 가리키는 것을 확인한 후 실행한다.

```text
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000 --no-access-log
```

`--no-access-log`는 callback query의 OAuth code·state가 Uvicorn access log에 남지 않도록 한다. 프록시/CDN의 access log도 query와 쿠키를 저장하지 않도록 구성한다.

## API·worker·frontend 실행

API와 별도 터미널에서, 같은 `backend/.env`를 사용하여 worker를 실행한다.

```text
uv run arq app.workers.arq_app.WorkerSettings
```

ARQ worker는 Linux 환경이나 저장소의 worker 컨테이너 사용을 권장한다. 로컬 Windows에서도 설치된 ARQ 0.28.0과 기본 `WorkerSettings`로 위 CLI의 시작·정상 종료 및 실제 GitHub 초기 수집 성공을 확인했다. API와 worker는 같은 DB·Redis·암호화 키를 사용해야 한다.

`frontend/.env.local`에 `VITE_USE_MSW=false`를 설정한 다음 `frontend/`에서 실행한다.

```text
npm ci
npm run dev
```

브라우저 주소는 `http://localhost:5173`으로 통일한다. Vite는 이 포트를 고정하며 다음 요청을 프록시한다.

| 브라우저 요청 | 내부 API 요청 |
| --- | --- |
| `/auth/github/login` | `/api/auth/github/login` |
| `/auth/github/link` | `/api/auth/github/link` |
| `/auth/github/callback?code=…&state=…` | `/api/auth/github/callback?code=…&state=…` |
| `/api/me` 등 | 같은 `/api/*` 경로 |

`oauthState` 쿠키는 공개 `/auth/github` 경로로 전송되며 10분 뒤 만료된다. callback은 브라우저 쿠키, Redis의 일회용 state, PKCE S256을 검증한다. 로그인은 새 `devon_session`을 발급하고 `/home`으로 이동한다. 재연동은 기존 세션과 GitHub 사용자 ID를 유지한다. 다른 GitHub 계정으로 바꾸려는 요청은 `409 github_already_linked`로 차단한다.

`devon_session`은 HttpOnly·Path `/`·SameSite Lax이며 로컬 HTTP에서는 Secure=false, 운영 HTTPS에서는 Secure=true다. 인증된 REST·SSE 연결·WS handshake에서 Redis TTL과 응답 쿠키를 14일로 연장한다. 만료·유실은 `401 unauthenticated`, Redis 장애는 `500 internal_error`다. `/auth/refresh`는 제공하지 않는다.

worker가 없으면 초기 수집이 진행되지 않아 홈이 `syncing`에 머무른다. 수집은 public 저장소의 목록 메타데이터만 저장한다. 정상 실패는 DB job에 기록하고 다음 로그인·재연동에서 다시 요청할 수 있다. SQL의 `queued` job이 Redis에서 유실되면 다음 로그인·재연동에서 재enqueue한다. 실행할 수 없는 ARQ 완료 기록만 남은 `queued` job은 실패로 정리하고 다음 요청에서 새로 시도한다. 재연동과 겹친 이전 토큰의 401은 DB의 새 토큰을 확인해 한 번 다시 요청하며 새 토큰을 이전 실패로 폐기하지 않는다.

프로세스가 강제로 종료된 `running` job은 자동 재실행하지 않는다. 운영자가 실제 worker 종료를 확인하고 해당 job을 실패로 정리한 뒤 재시도해야 한다. SQL의 업무 기록과 Redis 로그인 세션은 복구 정책이 다르며 유실된 로그인 세션은 다시 로그인한다.

## 검증

GitHub HTTP는 테스트 transport로 대체하고 PostgreSQL·Redis는 실제 격리 인스턴스를 사용한다. `TEST_DATABASE_URL`은 `_test`가 들어간 전용 DB, `TEST_REDIS_URL`은 테스트 전용 Redis DB 13·14·15 중 하나여야 한다. fixture가 지정한 SQL 테이블과 Redis DB를 비우므로 개발·운영 연결값을 재사용하지 않는다.

PowerShell 예시이며, 아래 DB·Redis는 먼저 별도로 준비한다.

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://devon@127.0.0.1:55433/devon_session_test'
$env:TEST_REDIS_URL='redis://127.0.0.1:56380/13'
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

환경변수가 없으면 통합 테스트는 skip되므로 통합 성공으로 해석하지 않는다. `frontend/`의 `npm test`는 Playwright가 MSW를 켜서 수행하는 화면 테스트다. 실제 Vite 프록시·API·DB·Redis·브라우저 쿠키 검증은 [FE 안내](../../frontend/README.md)의 별도 격리 환경에서 `npm run test:integration`으로 실행한다. 후자는 GitHub HTTP만 대체하며 실제 계정의 동의·운영 배포 검증과 구분한다.
