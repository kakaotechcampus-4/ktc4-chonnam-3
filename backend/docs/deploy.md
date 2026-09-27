# 배포 · 쿠키 · CI

PR #57의 게시본은 미병합 #45의 수집 구현과 해당 파일의 보안 보완을 포함하지 않는다. 아래 구성의 실제 API·worker 실행은 [인증 구현 기록](../../spec/backend/implementation-auth.md)의 선행 통합·후속 보완·재검증 조건을 충족한 뒤 진행한다. Compose 설정이 있다는 사실은 게시본 단독 실행이나 운영 배포 완료의 근거가 아니다.

## 1. 현재 저장소의 배포 구성

[`compose.deploy.yaml`](../../compose.deploy.yaml)은 `db`·`redis`·`migrate`·`api`·`worker`·`caddy`를
실행하도록 구성되어 있다. `migrate`가 `alembic upgrade head`를 완료해야 API와 worker가 시작한다.
[`frontend/Caddyfile.deploy`](../../frontend/Caddyfile.deploy)는 DuckDNS HTTPS origin 하나에서
FE 정적 파일과 API를 제공하며 공개 `/auth/github/*`에는 내부 `/api` 접두사를 붙여 전달한다.

```text
브라우저 -> https://devon-chonnam-3.duckdns.org -> EC2 / Caddy
                                                /       -> FE 정적 파일
                                                /api/*  -> api:8000
                                                /auth/github/* -> api:8000/api/auth/github/*
                                                api     -> app.main:app
                                                worker  -> ARQ initial_sync
                                                migrate / db / redis
```

`.env.deploy`를 준비한 뒤 저장소 루트에서 `docker compose -f compose.deploy.yaml up -d --build`로
시작한다. 새 DB 또는 migration 호환성을 확인한 DB를 사용한다. 이전 `0002`·`0003` OAuth migration이
적용된 volume은 이력·스키마부터 확인하며, 시작 오류를 피하려고 데이터를 삭제하거나 임의 stamp하지 않는다.

API는 `app.main:app --no-access-log`, worker는 `arq app.workers.arq_app.WorkerSettings`로 실행한다.
현재 worker에는 로그인 후 public 저장소 목록을 수집하는 `initial_sync`만 등록되어 있다.
AI 분석·면접 준비 작업까지 실행된다는 뜻은 아니며 큐 소비를 위해 worker가 계속 실행되어야 한다.

별도 `app.deploy_check:app`은 `/api/health`만 제공하는 점검 앱으로 남아 있으며 현재 compose의
실행 대상은 아니다. `ops/deploy.sh`의 health 성공은 GitHub 로그인·세션·worker까지 검증한 결과가
아니다. 이 문서는 저장소 설정을 설명하며 실제 운영 배포 완료 여부는 환경별 실행 결과로 확인한다.

이전 문서의 CloudFront + S3 + ALB는 검토 구조이며 현재 compose가 구현한 배포는 아니다.
후속 도입 시 3절의 CDN 주의사항을 적용하고 실제 인프라 계약을 다시 확인한다.

### 같은 origin을 유지하는 이유

서로 다른 사이트의 FE·BE로 나누면 인증 쿠키가 서드파티 쿠키 제한의 영향을 받을 수 있다.
`SameSite=None`만으로 브라우저의 서드파티 쿠키 정책을 우회할 수는 없다. FE·API·WS를 같은
HTTPS origin으로 제공하면 `SameSite=Lax`를 유지하고 CORS와 별도 WS 호스트를 피할 수 있다.

## 2. 쿠키

```
Set-Cookie: devon_session=...; HttpOnly; Secure; SameSite=Lax; Path=/
```

| 환경                | Secure | SameSite | CORS       |
| ------------------- | ------ | -------- | ---------- |
| local (vite 프록시) | false  | lax      | 불필요     |
| prod (같은 origin)  | true   | lax      | **불필요** |

`Secure` 는 prod 에서 유지한다 — same-origin 이어도 HTTPS 전용 쿠키여야 한다.

`FRONTEND_ORIGIN`은 OAuth callback의 origin과 상태 변경 요청·WS handshake의 Origin 검사에
사용하며 CORS allowlist가 아니다. 로컬과 운영 모두 같은 origin의 프록시를 사용한다.

세션은 Redis `auth:sess:{sid}`의 사용자 ID와 기본 14일 TTL로 관리한다. 인증된 REST·SSE·WS
handshake에서 같은 쿠키의 Max-Age와 Redis TTL을 연장한다. Redis 세션이 유실되면 재로그인하며
PostgreSQL에서 복원하지 않는다. 로그아웃은 현재 세션·쿠키만 삭제하고 GitHub 암호화 토큰은 유지한다.
Redis 장애는 인증 만료와 구분해 `500 internal_error`로 응답한다.

## 3. 프록시 설정

### ① SPA 폴백은 FE 정적 파일에만 적용한다

Caddy에서 API 라우트를 먼저 분기하고, `try_files {path} /index.html`은 FE 블록에만 둔다.
API 오류를 HTML 200으로 바꾸면 공통 오류 계약이 깨진다.

```
GET /api/interviews/{없는id}
  → BE: 404 + {"error":{"reason":"not_found"}}
  → 잘못된 프록시 fallback: 200 + index.html
  → FE: res.ok === true → JSON 파싱 실패
```

[error-reasons.md](error-reasons.md)의 오류 reason과 HTTP 상태를 그대로 전달한다.

### ② API와 OAuth 경로는 쿠키·헤더·쿼리를 전달한다

일반 API·SSE·면접 WS는 `/api` 아래에 둔다. 공개 OAuth 이동 경로 `/auth/github/*`는 Caddy가
`/api/auth/github/*`로 바꿔 전달한다. Caddy는 `/ws/*`도 전달하지만 면접의 공개 WS 경로는
`/api/ws/interviews/{sessionId}`다. `reverse_proxy`의 WebSocket Upgrade 지원을 사용하며
별도 브라우저 포트나 호스트를 노출하지 않는다.

OAuth callback의 `code`·`state` 쿼리와 인증 쿠키(`devon_session`)를 보존한다.
인증 응답을 캐시하거나 민감한 쿼리·쿠키·헤더를 로그에 남기지 않는다.

### ③ SSE — 압축을 끈다

[pipeline.md](pipeline.md) 3절의 프록시 버퍼링 경고를 따른다. Caddy의 API 라우트에는
FE 정적 파일용 압축·캐시를 섞지 않는다. 응답은 `Cache-Control: no-store`와 15초 keep-alive
코멘트(`: ping`)를 유지한다. `X-Accel-Buffering: no`는 Nginx 전용이므로 이것만으로 다른
프록시의 버퍼링이 꺼졌다고 판단하지 않는다.

### ④ WS 연결 종료와 사용자 이탈을 구분한다

텍스트 답변을 입력하는 동안에도 연결을 유지할 수 있도록 실제 프록시의 idle timeout을
검증한다. 연결 유지용 ping을 사용하더라도 이를 면접 상태의 자동 폐기 조건으로 쓰지 않는다.
Sprint 1은 [pipeline.md](pipeline.md) 4.3과 같이 disconnect·heartbeat·timeout만으로
`abandoned`를 설정하지 않는다.

### CloudFront를 추후 도입하는 경우

- SPA fallback은 기본 정적 behavior의 viewer-request rewrite로 한정한다. 배포 전체의 404를 HTML 200으로 바꾸지 않는다.
- `/api/*`는 `CachingDisabled`로 설정하고 쿠키·쿼리·Origin 및 WS Upgrade에 필요한 헤더를 전달한다. ALB의 Host 라우팅 여부에 따라 `AllViewer` 또는 `AllViewerExceptHostHeader`를 검토한다.
- `/auth/github/*`도 캐시하지 않고 code·state·쿠키를 보존하며 원본으로 전달할 때만 `/api`를 붙인다.
- SSE behavior의 자동 압축을 끄고 이벤트가 실제로 즉시 전달되는지 확인한다.
- CloudFront와 ALB 양쪽의 유휴 동작을 검증한다. timeout 조정이나 연결 유지가 자동 `abandoned` 정책 도입을 뜻하지는 않는다.

## 4. OAuth 콜백

운영 환경은 `APP_ENV=prod`, `COOKIE_SECURE=true`, HTTPS `FRONTEND_ORIGIN`을 사용한다.
`GITHUB_REDIRECT_URI`와 GitHub OAuth App의 Callback URL은 같은 origin의 공개 경로로 맞춘다.

```
https://devon-chonnam-3.duckdns.org/auth/github/callback
```

로그인·재연동은 이 callback 하나를 공유하고 일회용 state의 purpose로 구분한다. 별도 호환 경로
`/auth/github/link/callback`은 추가 등록할 필요가 없다. `read:user`만 요청하며 **Expire user access
tokens는 OFF**, `offline_access`는 사용하지 않는다. state는 일회 사용하며 코드 교환에 PKCE verifier를 전달한다.

프록시는 callback을 `/api/auth/github/callback`으로 전달하지만 코드 교환의 `redirect_uri`는
공개 주소를 유지한다. `oauthState` 쿠키의 Path는 `/auth/github`, 로그인 쿠키는 `/`다.
EC2 public IP·내부 API 호스트를 직접 등록하면 origin·쿠키 경로가 맞지 않는다.

콜백 URL 은 요청의 `Host` 헤더가 아니라 **`core/config.py` 의 설정값으로 만든다**
([layer-rules.md](layer-rules.md) — `os.environ` 단일 진입점).

## 5. 로컬 개발 — vite 프록시

`frontend/vite.config.ts`에는 아래 프록시가 구현되어 있으며 포트는 5173으로 고정된다.

```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
    '/auth/github': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (url) => `/api${url}`,
    },
  },
}
```

→ 로컬도 같은 오리진이 되어 prod 와 구조가 같아진다. CORS 설정이 필요 없고 `SameSite=lax` 로
충분하다.

실제 API를 사용할 때는 `frontend/.env.local`의 `VITE_USE_MSW=false`가 필요하다. API는
`uv run uvicorn app.main:app --reload --port 8000 --no-access-log`, worker는 별도 터미널에서
`uv run arq app.workers.arq_app.WorkerSettings`로 시작한다. 자세한 절차는 [로컬 OAuth 안내](local-oauth.md)를 따른다.

## 6. CI

`.github/workflows/backend-ci.yml` 을 **새로 추가**한다.

```yaml
on:
  pull_request:
    paths: ['backend/**', 'ai/**']
jobs: ruff → mypy → pytest (services: postgres:15, redis:7)
```

GitHub · Wanted · LLM 은 CI 에서 실제 호출하지 않고 mock 한다.

통합 테스트는 격리된 `TEST_DATABASE_URL`·`TEST_REDIS_URL`을 사용하며 앱 접속값으로 대체하지 않는다.
DB 이름에 `_test`를 포함하고 Redis DB는 13·14·15 중 테스트 전용 번호를 지정한다. 필요한 환경변수가
없으면 해당 통합 테스트는 skip된다. SQL TRUNCATE·Redis FLUSHDB 대상에 개발·운영 데이터를 지정하지 않는다.

CODEOWNERS 의 [팀 자유 영역] 이 팀 자체 CI 추가를 명시적으로 허용한다. 운영 3파일
(`assign-mentor` / `notify-discord` / `convention-check`)과 `CODEOWNERS` 만 건드리지 않으면 된다.

## 7. 브랜치 / PR

`frontend/README.md` 와 동일한 규칙이다.

- `develop` 에서 분기, PR 도 `develop` 으로
- 브랜치명 `feature/be-xxx`, `fix/be-xxx`
- `develop → main` PR 만 멘토 리뷰 + 컨벤션 봇 발동

## 8. 보안

이 repo 는 public 이다. 키를 코드·문서·노트북 본문에 붙여넣지 않는다. 실수했으면 지우는 게
아니라 **폐기(rotate)** 한다.

GitHub 토큰은 `BYTEA` + AES-GCM 으로 암호화해 저장한다 (`app/core/crypto.py`, 키는
`TOKEN_ENCRYPTION_KEY`). 평문 저장 금지.

- GitHub access token 을 FE 에 노출하지 않는다.
- 로그에 token · Authorization 헤더 · 쿠키 값을 남기지 않는다.
- OAuth callback의 code·state도 로그에 남기지 않는다. API access log를 끄고 프록시·CDN 수집 정책도 확인한다.
- private repo scope 를 요청하지 않는다.

## 9. 미결

| 항목 | 내용 |
|---|---|
| 인증 앱 운영 검증 | 저장소 compose는 `app.main:app`을 실행한다. 운영 환경값·migration·OAuth·재연동·로그아웃 실검증은 배포 시 확인 |
| Worker 운영 검증 | `initial_sync` worker 구성과 실제 큐 소비·실패 복구를 검증하며 미등록 분석·면접 작업은 별도 구현 |
| CDN·로드밸런서 | CloudFront·ALB·ECS 검토안은 현재 Caddy compose의 구현 완료 범위가 아님 |
| 배포 완료 기준 | deploy workflow·health 점검과 실제 서비스 기능 검증을 구분하며 운영 환경의 실행 결과를 별도 확인 |
