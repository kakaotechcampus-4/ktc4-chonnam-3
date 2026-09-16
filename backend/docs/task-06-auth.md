# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 근거: `spec/shared/decisions/0002-github-oauth.md`, `spec/shared/contracts/openapi.yaml`

## 목표

GitHub OAuth 로그인과 서버의 GitHub token 갱신, DEVON cookie 인증, refresh rotation, logout을 구현한다. 공개 API 범위는 `/api/auth/github/login`, callback, refresh, logout과 `/api/me`뿐이다. GitHub API용 내부 서비스는 `app.state.github.get(user_id, path)`로 제공한다.

## 작업

- GitHub OAuth App의 만료형 access/refresh token을 받고 FE에는 노출하지 않는다. 앱의 만료 옵션을 활성화하며 scope는 `read:user`만 요청한다.
- 새 OAuth 응답은 유효한 access/refresh token, `expires_in`, `refresh_token_expires_in`, `token_type=bearer`, `read:user` scope를 모두 요구한다. 누락·잘못된 응답은 저장하지 않고 `provider_unavailable`로 처리한다.
- 두 token은 AES-GCM으로 암호화해 `github_accounts.access_token_encrypted`, `refresh_token_encrypted`에 저장한다. 응답 TTL로 UTC `token_expires_at`, `refresh_token_expires_at`을 계산한다. `token_status`, `token_scope`를 유지하고 `token_type` 컬럼은 만들지 않는다.
- `0003`으로 세 신규 필드를 추가한다. 모두 NULL인 기존 비만료 token은 보존하며 다음 로그인에서 만료형 pair로 교체한다. 일부 필드만 NULL인 상태는 CHECK로 거부한다.
- GitHub API 호출은 `app.state.github.get(user_id, path)`가 대행하며 access 만료까지 60초 이하이면 요청 시 갱신한다. callback과 갱신은 같은 GitHub account row를 잠그고 최신 pair를 다시 확인한다. 새 token pair와 만료 시각은 함께 저장한다.
- refresh가 만료돼도 access가 유효하면 남은 수명 동안 사용한다. access까지 만료돼 갱신할 수 없거나 GitHub가 refresh를 거부하면 `token_status=revoked`를 commit한 뒤 `token_invalid`로 처리한다. 현재 access token의 API 401도 폐기하되 교체 전 token의 늦은 401은 새 pair를 폐기하지 않는다. 네트워크·429·5xx·잘못된 응답은 `provider_unavailable` 503이며 pair를 유지한다.
- `/api/me`는 GitHub 요청 없이 DB만 읽는다. valid 상태이며 access 또는 refresh가 사용 가능하면 `githubLinked=true`이고, 기존 비만료 token도 valid이면 true다. GitHub token 폐기는 DEVON JWT session을 폐기하지 않는다.
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
- GitHub 갱신용 공개 API·cron·worker를 만들지 않는다. 저장소 수집 pipeline 연결은 후속 범위다. GitHub rotation과 DB commit 사이 장애로 재로그인이 필요할 수 있음을 운영 문서에 기록한다.
- private repo scope는 요청하지 않는다.

## 완료 조건

- GitHub token 평문이 응답/log/DB에 남지 않는다.
- GitHub OAuth scope는 `read:user`만 사용한다.
- GitHub access/refresh pair를 암호화 저장하고 응답 TTL로 UTC 만료 시각을 계산한다. DEVON의 `auth_sessions.expires_at`과 구분한다.
- 새 로그인에서 비만료 응답·불완전한 pair·잘못된 TTL·type·scope를 거부하고 기존 pair를 손상시키지 않는지 검증한다.
- GitHub API 사용 시 만료 임박·만료 access의 갱신, 실제 PostgreSQL에서 동시 refresh·callback 저장 경합·늦은 401 보호, refresh 거부·만료의 폐기 commit을 검증한다.
- 네트워크·429·5xx·잘못된 응답이 `provider_unavailable` 503으로 처리되고 token을 폐기하지 않는지 검증한다. 원격 rotation과 DB commit에 정확히 한 번의 실행을 보장한다고 주장하지 않는다.
- `/api/me`의 valid/revoked, access/refresh 만료 조합, 기존 비만료 token 판정을 DB만으로 검증한다.
- migration `0003`의 기존 계정·암호화 token·DEVON session 보존, 세 필드 CHECK, downgrade 시 만료형 계정 폐기와 필드 제거를 검증한다. 서버 재시작 전 upgrade가 필요하며 downgrade는 비만료 token을 복원하지 않는다.
- migration `0002`의 기존 user generation backfill, 계정·암호화 token 보존, FK/INDEX, downgrade 후 재로그인 범위를 검증한다.
- suspended/withdrawn 사용자는 로그인 차단 reason을 반환한다.
- 실제 PostgreSQL로 rotation/replay와 폐기 commit, 동시 갱신, 재로그인 보호, logout 경합을 검증한다.
- Redis 유실·장애에도 기존 session의 refresh/logout은 성공하고 OAuth state 유실·장애는 안전하게 실패한다. DB 장애는 성공으로 숨기지 않는다.
- 누락·만료 session 거부, 이전 Redis token 거부, 만료 row만 정리와 반복 실행, Origin 검증이 계약대로 테스트된다.
