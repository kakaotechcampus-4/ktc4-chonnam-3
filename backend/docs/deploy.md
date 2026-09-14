# 배포 · 쿠키 · CI

## 1. 배포 구조 — DuckDNS + Caddy + EC2

FE·BE 를 **하나의 DuckDNS 도메인** 뒤에 둔다. 브라우저가 보는 호스트는 하나뿐이고, EC2 안에서는
Docker Compose 로 `caddy`, `api`, `worker`, `db`, `redis` 를 같이 띄운다.

```
브라우저 ── https://{name}.duckdns.org ──▶ EC2
                                      ┌─ Caddy :80/:443
                                      │  /          → FE 정적 파일
                                      │  /api/*     → api:8000
                                      │  /api/ws/*  → api:8000 (WebSocket Upgrade)
                                      └─ Docker Compose network
                                         api / worker / postgres / redis
```

### 왜 FE·BE 분리를 피하나

FE 가 Vercel, BE 가 EC2 처럼 **도메인이 갈리면** BE 가 심는 인증 쿠키가 브라우저 기준
**서드파티 쿠키**로 분류된다.

| | 분리 배포 | 단일 도메인 배포 |
|---|---|---|
| 쿠키 분류 | 서드파티 | 퍼스트파티 |
| Safari · iOS | 기본 차단 가능 | 정상 |
| Firefox | Total Cookie Protection 으로 분리 저장 | 정상 |
| 필요한 설정 | `SameSite=None; Secure` + CORS allowlist | `SameSite=Lax` |
| CSRF 방어 | `SameSite` 방어 약화 | `SameSite=Lax` 유지 |

`SameSite=None` 은 서드파티 쿠키 정책 자체를 우회하지 못한다. 따라서 무료 도메인이더라도
DuckDNS 로 FE·BE 를 한 origin 아래 묶고, Caddy 가 TLS 와 reverse proxy 를 맡는다.

### 이 구조가 없애는 것

- prod CORS 설정
- `SameSite=None` · 브라우저별 서드파티 쿠키 예외 처리
- WS 만 다른 도메인에 붙는 예외

## 2. 쿠키

```
Set-Cookie: devon_session=...; HttpOnly; Secure; SameSite=Lax; Path=/
```

| 환경 | Secure | SameSite | CORS |
|---|---|---|---|
| local (vite 프록시) | false | lax | 불필요 |
| prod (DuckDNS + Caddy) | true | lax | 불필요 |

`Secure` 는 prod 에서 유지한다. same-origin 이어도 HTTPS 전용 쿠키여야 한다.

`FRONTEND_ORIGIN` 은 prod 에서 CORS 용도로는 쓰이지 않는다. 로컬에서 vite 프록시를 쓰지 않는
경우의 allowlist 로만 남긴다.

## 3. Caddy 설정 — 반드시 지킬 것 4가지

### ① SPA 폴백을 API 라우트에 적용하지 않는다

SPA fallback(`try_files {path} /index.html`)은 FE 정적 파일 라우트에만 적용한다. `/api/*` 에까지
fallback 이 걸리면 BE 의 404 JSON 이 HTML 200 으로 바뀐다.

```
GET /api/interviews/{없는id}
  → BE: 404 + {"error":{"reason":"interview_not_found"}}
  → 잘못된 프록시 fallback: 200 + index.html
  → FE: res.ok === true → JSON 파싱 실패
```

[error-reasons.md](error-reasons.md) 의 reason 체계가 무력화되므로 Caddy 라우트는 API를 먼저
분기하고, SPA fallback 은 마지막 FE 정적 파일 블록에만 둔다.

```caddyfile
{name}.duckdns.org {
  handle /api/* {
    reverse_proxy api:8000
  }

  handle {
    root * /srv/frontend/dist
    try_files {path} /index.html
    file_server
  }
}
```

### ② `/api/*` 는 쿠키·헤더를 그대로 전달한다

브라우저가 보는 API, SSE, WS 경로는 모두 `/api` 아래에 둔다. `shared/api.ts` 의 fetch 래퍼는
자동으로 `/api` 를 붙이고, EventSource·WebSocket 은 래퍼를 거치지 않으므로 예시처럼 직접 붙인다.

| 브라우저 경로 | backend 역할 |
|---|---|
| `/api/auth/...` | 인증 API |
| `/api/analysis-runs/{runId}/events` | SSE |
| `/api/ws/interviews/{sessionId}` | WebSocket |

Caddy `reverse_proxy` 는 WebSocket Upgrade 를 지원한다. 별도 도메인이나 별도 포트를 브라우저에
노출하지 않는다.

### ③ SSE — API 라우트에서 압축·버퍼링을 피한다

[pipeline.md](pipeline.md) 3절의 프록시 버퍼링 경고가 Caddy 환경에도 그대로 적용된다.

- `encode gzip` 같은 압축 설정은 FE 정적 파일 블록에만 둔다.
- `/api/*` 블록에는 불필요한 압축·캐시 설정을 넣지 않는다.
- 응답 헤더는 `Cache-Control: no-store`, 15초 keep-alive 코멘트(`: ping`)를 유지한다.
- `X-Accel-Buffering: no` 는 Nginx 전용이지만, 프록시 교체 가능성을 위해 남겨도 무해하다.

### ④ WS idle timeout 은 앱 레벨 ping 으로 방어한다

스프린트1 은 텍스트 면접이라 **사용자가 답을 타이핑하는 동안 클라→서버 트래픽이 없다.**
기술 질문에 60초 넘게 쓰는 것은 정상 동작인데, 프록시나 네트워크 유휴 타임아웃과 겹치면
[pipeline.md](pipeline.md) 4.3 에 따라 `abandoned` 후보가 된다. 그러면 North Star(완주율)가
오염된다.

대응은 둘을 같이 한다.

- 앱 레벨 ping 을 유휴 타임아웃보다 짧은 주기로 보낸다.
- `ws:lock` 60초 하트비트를 그대로 쓰면 경계에서 아슬아슬하므로, ping 주기와 lock TTL 사이에
  여유를 둔다.

## 4. OAuth 콜백

`GITHUB_REDIRECT_URI` 는 prod 에서 **DuckDNS 도메인**을 가리켜야 한다.

```
https://{name}.duckdns.org/api/auth/github/callback
```

EC2 public DNS, public IP, 컨테이너 포트를 직접 넣으면 쿠키가 그 호스트에 심겨 1절의 문제가
재발한다. GitHub OAuth App 설정의 Callback URL 도 같이 맞춘다.

콜백 URL 은 요청의 `Host` 헤더가 아니라 **`core/config.py` 의 설정값으로 만든다**
([layer-rules.md](layer-rules.md) — `os.environ` 단일 진입점).

## 5. 로컬 개발 — vite 프록시

`frontend/vite.config.ts` 에 프록시를 추가해야 한다 (현재 없음 — **FE 작업 항목**).

```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
  },
}
```

WS 도 브라우저에서 `/api/ws/interviews/{sessionId}` 로 붙으므로 위 `/api` 프록시에 같이 걸린다.
로컬도 prod 와 같은 same-origin 구조가 되어 CORS 설정이 필요 없고 `SameSite=lax` 로 충분하다.

## 6. CI

`.github/workflows/backend-ci.yml` 을 **새로 추가**한다.

```yaml
on:
  pull_request:
    paths: ['backend/**', 'ai/**']
jobs: ruff → mypy → pytest (services: postgres:15, redis:7)
```

GitHub · Wanted · LLM 은 CI 에서 실제 호출하지 않고 mock 한다.

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
- private repo scope 를 요청하지 않는다.

## 9. 미결

| 항목 | 내용 |
|---|---|
| DuckDNS 이름 | 최종 도메인 이름 확정 필요 |
| FE 빌드 배치 | Caddy 이미지에 FE dist 를 포함할지, EC2 배포 스크립트가 volume 으로 둘지 결정 필요 |
| compose 위치 | 현재 `backend/docker-compose.yml` 은 BE 로컬 개발 중심이다. prod compose 는 FE/Caddy 포함 형태로 별도 작성 필요 |
| CD | GitHub Actions 사용 확정. EC2 배포 방식 확정 후 작성 |
