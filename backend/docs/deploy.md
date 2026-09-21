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
DB 연결·migration, OAuth App의 callback과 배포 검증을 함께 준비해야 한다. 이번 병합은
배포 점검 앱을 인증 앱으로 바꾸거나 운영 로그인을 활성화하지 않는다.

이전 문서의 CloudFront + S3 + ALB는 검토 구조이며 현재 compose가 구현한 배포는 아니다.
후속 도입 시 3절의 CDN 주의사항을 적용하고 실제 인프라 계약을 다시 확인한다.

### 같은 origin을 유지하는 이유

서로 다른 사이트의 FE·BE로 나누면 인증 쿠키가 서드파티 쿠키 제한의 영향을 받을 수 있다.
`SameSite=None`만으로 브라우저의 서드파티 쿠키 정책을 우회할 수는 없다. FE·API·WS를 같은
HTTPS origin으로 제공하면 `SameSite=Lax`를 유지하고 CORS와 별도 WS 호스트를 피할 수 있다.

## 2. 쿠키

| 쿠키 | Path | 수명 |
|---|---|---|
| `accessToken` | `/` | 15분 |
| `refreshToken` | `/api/auth` | 14일, rotation 시 갱신 |
| `oauthState` | `/api/auth/github` | 10분, callback에서 삭제 |

세 쿠키는 HttpOnly, SameSite=Lax, Domain 미설정이다. `Secure`는 prod에서 true이고 local HTTP에서는 false다.

| 환경                | Secure | SameSite | CORS       |
| ------------------- | ------ | -------- | ---------- |
| local (vite 프록시) | false  | lax      | 불필요     |
| prod (같은 HTTPS origin) | true | lax | 불필요 |

`Secure` 는 prod 에서 유지한다 — same-origin 이어도 HTTPS 전용 쿠키여야 한다.

`FRONTEND_ORIGIN`은 refresh/logout의 `Origin`을 exact match하는 보안 경계다. local은
`http://localhost:5173`, prod는 실제 HTTPS origin 하나를 trailing slash 없이 설정한다.

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

OAuth callback의 `code`·`state` 쿼리, 인증 쿠키, refresh/logout의 `Origin`을 보존한다.
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

`frontend/vite.config.ts`의 `/api` 프록시는 `http://localhost:8000`을 향한다.

```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
  },
}
```

WS도 `/api/ws/interviews/{sessionId}`를 사용한다. 실제 WS 기능을 연결할 때는 Vite 프록시의
WebSocket 전달 설정도 함께 확인한다.
로컬도 prod 와 같은 same-origin 구조가 되어 CORS 설정이 필요 없고 `SameSite=lax` 로 충분하다.
GitHub OAuth App의 local callback과 `GITHUB_REDIRECT_URI`는 브라우저 origin을 거치는
`http://localhost:5173/api/auth/github/callback`으로 맞춘다.

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

## 10. Refresh 저장소 전환과 정리

### 전환 순서

1. DB를 기존 운영 절차로 백업하고 구버전 인증 인스턴스의 트래픽을 중지한다. 진행 중인 callback·refresh·logout을 종료한 뒤 구버전을 내린다. Redis 원본과 DB 원본 버전을 동시에 서비스하지 않는다.
2. backend 디렉터리에서 `uv run alembic upgrade head`를 실행한다. `0001`의 계정·GitHub token은 유지하고 `0002`에서 `users.refresh_generation`을 채우며 `auth_sessions`를 생성한다.
3. 새 DB 원본 버전만 시작한다. 이전 `auth:refresh:*` Redis 키는 읽거나 가져오지 않는다. 기존 Access는 최대 15분간 남고, 이전 Refresh로 갱신하려면 재로그인이 필요하다. 이전 키는 TTL로 자연 만료시키며 다른 Redis 데이터와 함께 비우지 않는다.
4. 신규 로그인·갱신·로그아웃과 만료 정리 명령을 확인한다. Redis 장애 시 기존 session의 갱신·로그아웃은 계속 처리되고 신규 OAuth는 안전하게 실패해야 한다. DB 장애 시 유효 토큰의 갱신·로그아웃은 503이며 쿠키를 지우거나 성공으로 응답하지 않아야 한다.

`0002` downgrade는 `auth_sessions`와 user generation을 제거하지만 `0001`의 계정은 보존한다. DB 로그인 기록은 잃으므로 재로그인이 필요하다. **아직 TTL이 남은 Redis 키를 읽는 구버전을 되살리는 것은 안전한 인증 롤백이 아니다.** 되돌릴 버전도 이전 Refresh를 승인하지 않는 전환 기준을 적용해야 하며, 구버전과의 무중단 혼합 운영·자동 fallback은 지원하지 않는다.

### 과거 DB 백업 복원 시

PostgreSQL의 정상적인 장애 복구와 과거 시점의 백업 복원은 구분한다. 과거 백업에는 로그아웃·재사용 탐지 이전의 session이 남아 있을 수 있으므로 DB를 사용한다는 이유만으로 폐기 기록의 되돌림이 방지되지는 않는다. 과거 백업을 복원했다면 인증 트래픽을 재개하기 전에 아래 정리를 한 트랜잭션으로 수행하고 모든 사용자에게 재로그인을 요구한다. 사용자·GitHub 계정은 보존하며, 이 명령은 일반 재시작이나 정기 만료 정리 때 실행하지 않는다.

```sql
BEGIN;
UPDATE users SET refresh_generation = gen_random_uuid();
DELETE FROM auth_sessions;
COMMIT;
```

이는 Refresh 기록 초기화이며 이미 발급된 Access JWT의 즉시 폐기를 의미하지 않는다. 기존 Access는 최대 15분간 유효할 수 있다.

### 만료 기록 정리

DB 전용 설정은 `DATABASE_URL`을 환경 변수 또는 backend `.env`에서 읽는다. Alembic과 정리 명령에는 GitHub·JWT·암호화 비밀값이나 Redis가 필요하지 않다. 정리 명령은 아래와 같다.

```bash
uv run python -m scripts.cleanup_auth_sessions
```

현재 UTC 기준 `expires_at`이 지난 row만 한 트랜잭션에서 삭제한다. 아직 만료되지 않은 session은 삭제하지 않으며 반복 실행해도 안전하다. generation 변경으로 이미 무효화된 row도 만료 시 정리된다. 로그아웃한 row는 즉시 삭제되므로 별도 보존 대상이 아니다. 출력·로그에는 삭제 개수만 남기고 JWT·cookie·GitHub token·사용자 식별자는 남기지 않는다.

기존 운영 스케줄러에서 **매시간 1회** 실행한다. Linux cron을 이미 사용하는 환경에서의 예시는 다음과 같다. backend 작업 경로와 Python 경로를 실제 배포에 맞추고 DB 설정을 해당 실행 환경에 제공한다.

```cron
0 * * * * cd /srv/backend && /srv/backend/.venv/bin/python -m scripts.cleanup_auth_sessions
```

Windows 로컬에서는 backend 작업 디렉터리에서 `.venv\Scripts\python.exe -m scripts.cleanup_auth_sessions`로 수동 확인한다. 운영 정기 실행 등록은 기존 배포 스케줄러 책임이며 이 구현이 cron·작업 스케줄러를 자동 등록하지 않는다. 새로운 스케줄러 라이브러리나 API lifespan 정리 loop는 추가하지 않는다. 정리가 늦어져도 만료 검증이 접속을 차단하지만 불필요한 DB row가 쌓이므로 실패를 확인하고 재실행한다.
