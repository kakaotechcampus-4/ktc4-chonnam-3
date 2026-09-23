# 배포 · 쿠키 · CI

## 현재 저장소의 배포 구성 — Caddy + Compose

저장소 루트의 [`compose.deploy.yaml`](../../compose.deploy.yaml)은 `db`·`redis`·`migrate`·`api`·`worker`·`caddy`를 실행한다. `migrate`가 `alembic upgrade head`를 완료해야 API와 worker가 시작한다. Caddy는 FE 파일을 제공하고 `/api/*`를 API로 전달한다. 공개 `/auth/github/*`에는 `/api`를 붙여 전달하므로 브라우저 callback과 내부 API 경로가 다르다. 설정은 [`frontend/Caddyfile.deploy`](../../frontend/Caddyfile.deploy)에 있다.

새 DB 또는 migration 호환성을 검토한 DB를 대상으로 `.env.deploy`를 준비한 뒤, 저장소 루트에서 `docker compose -f compose.deploy.yaml up -d --build`를 실행한다. 기존 volume에 이전 `0002`·`0003` OAuth migration이 적용되어 있다면 먼저 이력·스키마를 검토한다. 자동 migration을 성공시키기 위해 기존 데이터를 삭제하거나 Alembic 이력을 임의로 stamp하지 않는다.

API는 `--no-access-log`로 시작하고 worker는 `arq app.workers.arq_app.WorkerSettings`를 실행한다. worker는 로그인 후 public 저장소 목록 메타데이터를 수집하며 AI 분석 worker까지 등록한 것은 아니다. 큐 소비를 위해 worker가 계속 실행되어야 한다. 현재 저장소의 배포 구성 검증과 실제 운영 배포 완료는 별개다.

운영 환경은 `APP_ENV=prod`, `COOKIE_SECURE=true`, HTTPS `FRONTEND_ORIGIN`, 동일 origin의 `/auth/github/callback`을 `GITHUB_REDIRECT_URI`로 설정한다. GitHub OAuth App에는 이 공개 callback 하나를 등록하며 로그인·재연동이 함께 사용한다. `read:user`만 요청하고 **Expire user access tokens는 OFF**, `offline_access`는 사용하지 않는다.

## 1. 배포 구조 — AWS 통합 검토안

아래 CloudFront·ALB 내용은 AWS로 옮길 때의 검토안이다. 현재 Compose/Caddy 배포에 CloudFront·ALB가 이미 구성되었다는 뜻은 아니다.

FE·BE 를 **하나의 CloudFront 배포** 뒤에 둔다. 브라우저가 보는 호스트는 하나뿐이다.

```
                    ┌─ CloudFront (단일 도메인) ─┐
브라우저  ─────────▶ │  /          → S3 (FE 정적)  │
                    │  /api/*     → ALB → api     │
                    │  /auth/github/* → ALB → api │
                    │  /ws/*      → ALB → worker* │
                    └────────────────────────────┘
                       * api 컨테이너가 WS 도 받는다. ALB 뒤의 실행 방식
                         (EC2 + compose / ECS)은 미결.
```

### 왜 Vercel + AWS 분리를 접었나

FE 가 Vercel, BE 가 AWS 면 **도메인이 갈린다.** 그러면 BE 가 심는 인증 쿠키가 브라우저 기준
**서드파티 쿠키**로 분류된다.

|              | 분리 배포                                                 | 통합 배포              |
| ------------ | --------------------------------------------------------- | ---------------------- |
| 쿠키 분류    | 서드파티                                                  | 퍼스트파티             |
| Safari · iOS | **기본 차단 → 로그인 불가**                               | 정상                   |
| Firefox      | Total Cookie Protection 으로 분리 저장 → 사실상 동작 불가 | 정상                   |
| 필요한 설정  | `SameSite=None; Secure` + CORS allowlist                  | `SameSite=Lax` 만      |
| CSRF 방어    | `SameSite` 방어가 사라져 별도 토큰 필요                   | `SameSite=Lax` 로 유지 |

⚠ **`SameSite=None` 으로는 해결되지 않는다.** 차단은 `SameSite` 와 별개인 **서드파티 쿠키
정책 레이어**에서 일어난다. iOS 는 브라우저 앱과 무관하게 WebKit 을 쓰므로 앱을 바꿔도 같다.

검토한 대안은 도메인 구입(`devon.dev` / `api.devon.dev` 로 상위 도메인 공유 → same-site 성립)
이었고, 비용이 들지 않는 **AWS 통합**을 택했다.

> `*.vercel.app` 과 `*.cloudfront.net` 은 Public Suffix List 에 있어 `Domain=` 으로 서브도메인
> 간 쿠키를 공유할 수 없다. "도메인만 맞추면 된다" 가 성립하려면 **커스텀 도메인이 필요**했다.

### 이 구조가 없애는 것

- CORS 설정 (same-origin 이므로 preflight 자체가 없다)
- `SameSite=None` · `Secure` 조합에 대한 브라우저별 분기
- WS 만 다른 도메인에 붙는 예외 (`/ws/*` 도 같은 호스트다)

## 2. 쿠키

```
Set-Cookie: devon_session=...; HttpOnly; Secure; SameSite=Lax; Path=/
```

| 환경                | Secure | SameSite | CORS       |
| ------------------- | ------ | -------- | ---------- |
| local (vite 프록시) | false  | lax      | 불필요     |
| prod (CloudFront)   | true   | lax      | **불필요** |

`Secure` 는 prod 에서 유지한다 — same-origin 이어도 HTTPS 전용 쿠키여야 한다.

`FRONTEND_ORIGIN`은 OAuth callback의 origin 검증과 상태 변경 요청·WS handshake의 Origin 검사에 사용한다. 현재 API는 별도 CORS allowlist를 제공하지 않으므로 로컬도 Vite 프록시를 사용한다.

세션은 Redis `auth:sess:{sid}`의 사용자 ID와 14일 TTL로 관리한다. 인증된 REST·SSE·WS handshake 응답에 같은 쿠키의 Max-Age를 1,209,600초로 연장한다. Redis가 비면 다시 로그인하며 PostgreSQL에서 로그인 세션을 복원하지 않는다. 로그아웃은 현재 Redis 세션과 쿠키만 삭제하고 GitHub 암호화 토큰은 유지한다. Redis 장애는 인증 만료와 구분해 `500 internal_error`로 응답한다.

## 3. CloudFront 설정 — 반드시 지킬 것 4가지

CDN 기본값이 API·SSE·WS 와 충돌한다. 아래는 선택이 아니라 **안 하면 깨지는 항목**이다.

### ① SPA 폴백을 Custom Error Response 로 만들지 않는다 🚨

`vercel.json` 이 하던 SPA 폴백(`/(.*)` → `index.html`)을 CloudFront **Custom Error Response**
(404 → `/index.html`, 200)로 옮기면 안 된다. **이 설정은 배포 전체에 적용되어 behavior 별로 끌
수 없다.**

```
GET /api/interviews/{없는id}
  → BE: 404 + {"error":{"reason":"interview_not_found"}}
  → CloudFront: "404 네? index.html 줘야지" → 200 + HTML
  → FE: res.ok === true → JSON 파싱 실패
```

[error-reasons.md](error-reasons.md) 의 reason 체계가 통째로 무력화된다. **기본 behavior 에만
적용되는 CloudFront Function(viewer request)으로 rewrite 한다.**

### ② `/api/*` · `/auth/github/*` · `/ws/*` 는 캐시를 끄고 전체를 전달한다

CloudFront 는 캐시 적중률을 위해 **기본적으로 쿠키·헤더를 원본에 넘기지 않는다.** 그대로 두면
쿠키 없이 도착해 전부 401 이다.

| behavior   | 캐시 정책         | 오리진 요청 정책                                                         |
| ---------- | ----------------- | ------------------------------------------------------------------------ |
| `/api/*`   | `CachingDisabled` | `AllViewer` (ALB 가 host 기반 라우팅을 쓰면 `AllViewerExceptHostHeader`) |
| `/auth/github/*` | `CachingDisabled` | query·Cookie·Set-Cookie 보존, 원본으로 전달할 때 `/api` prefix 추가 |
| `/ws/*`    | `CachingDisabled` | 위와 동일 — `Upgrade` · `Connection` 헤더 전달에 필요                    |
| `/` (기본) | 정적 캐시         | 최소                                                                     |

### ③ SSE — 압축을 끈다

[pipeline.md](pipeline.md) 3절의 프록시 버퍼링 경고가 CloudFront 에도 그대로 적용된다.
추가로 **자동 압축(Compress objects automatically)을 꺼야 한다.** 켜져 있으면 gzip 버퍼링으로
이벤트가 뭉쳐 나가 4-2-v2 진행바가 끊기거나 한꺼번에 튄다.

응답 헤더는 기존대로 `Cache-Control: no-store` + `X-Accel-Buffering: no`, 15초 keep-alive 유지.

### ④ ALB 유휴 타임아웃을 올린다 — 면접 기능 직결 🚨

ALB 기본 유휴 타임아웃은 **60초**다. WS 연결에 60초간 프레임이 없으면 끊는다.

스프린트1 은 텍스트 면접이라 **사용자가 답을 타이핑하는 동안 클라→서버 트래픽이 없다.**
기술 질문에 60초 넘게 쓰는 것은 정상 동작인데, 그 순간 연결이 끊기면 답변 입력·재연결에 지장이 생긴다.
[pipeline.md](pipeline.md) 4.3에 따라 연결 끊김만으로 `abandoned`를 판정하지 않는다. 명시적 이탈·레포 재선택만 해당하며 timeout 기반 자동 이탈 처리는 Sprint 1에 없다.

대응은 둘을 같이 한다.

- ALB `idle_timeout.timeout_seconds` 를 면접 길이(`INTERVIEW_DURATION_SECONDS=1200`) 이상으로
- 앱 레벨 ping 을 **타임아웃보다 짧은 주기**로 — `ws:lock` 60초 하트비트를 그대로 쓰면 경계에서
  아슬아슬하다. 주기를 줄이거나 타임아웃을 올려 여유를 둔다

⚠ CloudFront 에도 자체 유휴 동작이 있으므로 **ALB 설정만으로는 부족하다.** 앱 레벨 ping 은
어느 쪽이든 필수다.

## 4. OAuth 콜백

`GITHUB_REDIRECT_URI` 는 prod 에서 **CloudFront 도메인**을 가리켜야 한다.

```
https://{public-domain}/auth/github/callback
```

⚠ ALB · EC2 주소를 직접 넣으면 **쿠키가 그 호스트에 심겨 1절의 문제가 그대로 재발한다.**
GitHub OAuth App 설정의 Callback URL도 같은 공개 주소로 맞춘다. 로그인과 재연동은 하나의 callback을 공유하며 서버에 저장된 일회용 state의 purpose로 구분한다. `/auth/github/link/callback`은 호환 경로로만 남아 있으며 추가 등록할 필요가 없다.

콜백 URL 은 요청의 `Host` 헤더가 아니라 **`core/config.py` 의 설정값으로 만든다**
([layer-rules.md](layer-rules.md) — `os.environ` 단일 진입점).

프록시는 callback을 `/api/auth/github/callback`으로 전달하고 code·state query와 쿠키를 보존한다. 코드 교환 시 GitHub에 보내는 `redirect_uri`는 내부 `/api` 경로가 아니라 위 공개 주소다. `oauthState`의 Path는 `/auth/github`, 로그인 쿠키의 Path는 `/`다.

## 5. 로컬 개발 — vite 프록시

`frontend/vite.config.ts`에 아래 프록시가 구현되어 있다. Vite 포트는 5173으로 고정된다.

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

실제 API를 연결할 때는 `frontend/.env.local`의 `VITE_USE_MSW=false`가 필요하다. API는 `uv run uvicorn app.main:app --reload --port 8000 --no-access-log`, worker는 별도 터미널에서 `uv run arq app.workers.arq_app.WorkerSettings`로 시작한다. 전체 절차와 기존 DB 주의사항은 [로컬 OAuth 안내](local-oauth.md)를 따른다.

## 6. CI

`.github/workflows/backend-ci.yml` 을 **새로 추가**한다.

```yaml
on:
  pull_request:
    paths: ['backend/**', 'ai/**']
jobs: ruff → mypy → pytest (services: postgres:15, redis:7)
```

GitHub · Wanted · LLM 은 CI 에서 실제 호출하지 않고 mock 한다.

현재 PostgreSQL/Redis 통합 fixture는 `TEST_DATABASE_URL`·`TEST_REDIS_URL`만 사용한다. DB 이름에는 `_test`가 포함되어야 하고 Redis DB는 13·14·15 중 테스트 전용 번호를 지정해야 한다. 두 변수가 없으면 관련 테스트는 skip된다. fixture의 SQL TRUNCATE와 Redis FLUSHDB 대상에 개발·운영 데이터를 지정하지 않는다.

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
- OAuth callback의 code·state query도 로그에 남기지 않는다. API access log는 끄고 프록시·CDN의 수집 정책도 확인한다.
- private repo scope 를 요청하지 않는다.

## 9. 미결

| 항목             | 내용                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| ALB 뒤 실행 방식 | EC2 + docker compose / ECS. 멘토 의견 대기 중                                                                      |
| ALB 생략 여부    | CloudFront → EC2 직접(custom origin)도 가능하다. ALB 비용은 없어지지만 헬스체크·무중단 배포·다중 인스턴스를 잃는다 |
| 커스텀 도메인    | `*.cloudfront.net` 기본 도메인으로도 동작한다. 데모용 도메인이 필요하면 ACM 인증서와 함께 추가                     |
| CD               | GitHub Actions 사용 확정. 대상 인프라 확정 후 작성                                                                 |
