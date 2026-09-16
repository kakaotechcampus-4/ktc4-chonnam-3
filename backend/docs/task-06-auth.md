# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 근거: `spec/shared/decisions/0002-github-oauth.md`, `spec/shared/contracts/openapi.yaml`

## 목표

GitHub OAuth 로그인, DEVON cookie 인증, refresh rotation, logout을 구현한다. 현재 범위는 `/api/auth/github/login`, callback, refresh, logout과 `/api/me`뿐이다.

## 작업

- GitHub OAuth callback에서 GitHub access token을 받고 FE에는 노출하지 않는다.
- GitHub token은 암호화해 `github_accounts.access_token_encrypted`에 저장한다.
- GitHub OAuth App long-lived access token을 전제로 한다.
- Expiring-token 관련 필드가 포함된 GitHub token 응답은 저장하지 않고 `provider_unavailable`로 실패 처리한다.
- `github_accounts` token field는 `access_token_encrypted`, `token_status`, `token_scope`만 둔다.
- `token_type`, `token_expires_at`, `refresh_token_encrypted`, `refresh_token_expires_at`는 만들지 않는다.
- GitHub API 호출은 BE가 대행한다.
- OAuth state는 `auth:oauth:{state}`에 600초 저장하고 browser-bound single-use cookie와 S256 PKCE를 검증한다.
- DEVON HS256 access/refresh JWT를 생성해 HttpOnly, SameSite=Lax cookie로만 전달한다. body로 반환하지 않는다.
- access는 900초, refresh는 rotation마다 1,209,600초다. refresh 상태는 PostgreSQL `users.refresh_generation`과 `auth_sessions`에만 저장한다. raw JWT 저장, Redis 이중 기록/fallback은 금지한다.
- 발급·갱신·로그아웃은 user row를 먼저 잠근 뒤 session을 처리한다. rotation은 `refresh_jti`와 `expires_at`을 한 트랜잭션에서 교체한다.
- 같은 generation의 유효 session에서 이전 `jti` 재사용이 감지되면 user generation을 바꾸고 commit한 뒤 401을 반환한다. 이미 무효인 generation과 누락·만료 session은 다른 로그인을 폐기하지 않는다.
- 로그아웃은 `sid`·사용자·generation이 같은 DB row만 삭제하며 직전 rotation으로 `jti`가 바뀌어도 폐기한다. 기존 Access JWT는 최대 15분간 유효하다.
- refresh/logout은 Redis를 사용하지 않는다. 유효한 토큰에 대한 DB 장애는 503이며 cookie 삭제나 폐기 성공으로 응답하지 않는다. refresh cookie가 없거나 검증 실패인 로그아웃은 cookie만 멱등 삭제한다.
- `0001`은 유지하고 `0002`로 Refresh 테이블과 user generation을 추가한다. 이전 Redis 기록은 가져오지 않으므로 기존 로그인은 재로그인이 필요하다.
- 만료 session은 `python -m scripts.cleanup_auth_sessions`로 정기 삭제한다. 명령은 DB 설정만 사용하고 API 프로세스의 lifespan에 정리 작업을 만들지 않는다.
- DEVON JWT payload에는 GitHub access token을 넣지 않는다.
- access/refresh 공통 claim은 `sub`, `iat`, `exp`, `jti`, issuer, audience, type이고 refresh는 `sid`, `generation`을 추가한다.
- refresh/logout은 요청 `Origin`이 정확한 `FRONTEND_ORIGIN`과 일치해야 한다.
- callback은 신규/기존 GitHub 사용자를 수렴시켜 로그인만 완료한다. `initial_sync`를 enqueue하거나 link API를 만들지 않는다.
- private repo scope는 요청하지 않는다.

## 완료 조건

- GitHub token 평문이 응답/log/DB에 남지 않는다.
- GitHub OAuth scope는 `read:user`만 사용한다.
- `github_accounts`에는 GitHub refresh token/expiry 컬럼을 추가하지 않는다. DEVON의 `auth_sessions.expires_at`과 혼동하지 않는다.
- migration `0002`의 기존 user generation backfill, 계정·암호화 token 보존, FK/INDEX, downgrade 후 재로그인 범위를 검증한다.
- suspended/withdrawn 사용자는 로그인 차단 reason을 반환한다.
- 실제 PostgreSQL로 rotation/replay와 폐기 commit, 동시 갱신, 재로그인 보호, logout 경합을 검증한다.
- Redis 유실·장애에도 기존 session의 refresh/logout은 성공하고 OAuth state 유실·장애는 안전하게 실패한다. DB 장애는 성공으로 숨기지 않는다.
- 누락·만료 session 거부, 이전 Redis token 거부, 만료 row만 정리와 반복 실행, Origin 검증이 계약대로 테스트된다.
