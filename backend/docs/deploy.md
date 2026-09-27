# 배포 · 쿠키 · CI

## 1. 현재 배포 점검 구조

저장소의 `compose.deploy.yaml`과 `frontend/Caddyfile.deploy`는 EC2에서 DuckDNS + Caddy로
FE 정적 파일과 API를 한 origin으로 제공한다. 실제 실행 앱은 `app.deploy_check:app`이며
`/api/health`만 제공하는 배포 점검용이다. `ops/deploy.sh`의 health 성공은 GitHub 로그인,
DB migration, worker 또는 전체 서비스의 배포 성공을 뜻하지 않는다.

```text
브라우저 -> https://devon-chonnam-3.duckdns.org -> EC2 / Caddy
                                                /       -> FE 정적 파일
                                                /api/*  -> api:8000
                                                api     -> app.deploy_check:app
                                                db / redis
```

인증 API는 별도 실행 진입점 `app.main:app`에 있다. 인증 앱으로 배포를 전환하려면 환경변수,
DB 연결·migration, OAuth App의 callback과 배포 검증을 함께 준비해야 한다. 현재 배포는
배포 점검 앱이며 운영 로그인은 활성화되어 있지 않다.

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

BE 는 CORS 미들웨어를 두지 않는다 — local·prod 모두 same-origin 이다. `FRONTEND_ORIGIN` 은
CORS allowlist 로 쓰지 않는다.

## 3. 프록시 설정

### ① SPA 폴백은 FE 정적 파일에만 적용한다

Caddy에서 API 라우트를 먼저 분기하고, `try_files {path} /index.html`은 FE 블록에만 둔다.
API 오류를 HTML 200으로 바꾸면 공통 오류 계약이 깨진다.

```
GET /api/interviews/{없는id}
  → BE: 404 + {"error":{"reason":"interview_not_found"}}
  → 잘못된 프록시 fallback: 200 + index.html
  → FE: res.ok === true → JSON 파싱 실패
```

[error-reasons.md](error-reasons.md)의 오류 reason과 HTTP 상태를 그대로 전달한다.

### ② `/api/*`는 쿠키·헤더·쿼리를 전달한다

인증, SSE와 WS의 브라우저 경로는 `/api` 아래에 둔다. 현재 Caddy 설정은 `/api/*`와 `/ws/*`를
API로 전달하지만 면접의 공개 WS 경로는 `/api/ws/interviews/{sessionId}`다. `reverse_proxy`의
WebSocket Upgrade 지원을 사용하며 별도 브라우저 포트나 호스트를 노출하지 않는다.

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
- SSE behavior의 자동 압축을 끄고 이벤트가 실제로 즉시 전달되는지 확인한다.
- CloudFront와 ALB 양쪽의 유휴 동작을 검증한다. timeout 조정이나 연결 유지가 자동 `abandoned` 정책 도입을 뜻하지는 않는다.

## 4. OAuth 콜백

`GITHUB_REDIRECT_URI`는 인증 앱 배포 시 **브라우저가 사용하는 HTTPS origin**을 가리켜야 한다.
현재 배포 점검 도메인을 인증에도 사용할 경우의 등록 예시는 다음과 같다. 점검 앱에는
callback API가 없으므로 이 주소 등록만으로 운영 로그인이 동작하지 않는다.

```
https://devon-chonnam-3.duckdns.org/api/auth/github/callback
```

EC2 public IP·내부 API 호스트를 직접 넣으면 쿠키 origin이 달라진다.
GitHub OAuth App 설정의 Callback URL 도 같이 맞춘다.

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

WS도 `/api/ws/interviews/{sessionId}`를 사용하므로 프록시에 WebSocket 전달(`ws: true`)도 함께 켠다.

→ 로컬도 같은 오리진이 되어 prod 와 구조가 같아진다. CORS 설정이 필요 없고 `SameSite=lax` 로
충분하다.

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
| 인증 앱 운영 전환 | 현재 compose는 `app.deploy_check:app`이다. `app.main:app` 전환, 환경값·migration·OAuth 실검증은 후속 배포 작업 |
| Worker 운영 | 현재 compose에는 worker가 없다. 분석 기능과 함께 구현·등록·관측 검증 필요 |
| CDN·로드밸런서 | CloudFront·ALB·ECS 검토안은 현재 Caddy compose의 구현 완료 범위가 아님 |
| 배포 완료 기준 | deploy workflow·health 점검과 실제 서비스 기능 검증을 구분하며 운영 환경의 실행 결과를 별도 확인 |
