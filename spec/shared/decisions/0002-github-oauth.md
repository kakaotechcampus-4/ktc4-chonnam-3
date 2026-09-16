# 0002 GitHub OAuth와 DEVON 세션
- 상태: Accepted
- 작성일: 2026-09-14
- 갱신일: 2026-09-17, GitHub OAuth App 만료형 token과 서버 갱신 사용자 승인
- 관련 PR: 없음
- 검토자: 사용자 승인, FE·BE 공동 적용

## 맥락

GitHub OAuth 로그인과 DEVON 인증의 전달 방식, refresh 저장소, 재사용 대응이 문서마다 달랐다. 로그인과 현재 사용자 확인에 더해, 2026-09-17 사용자 승인으로 GitHub OAuth App의 만료형 access/refresh token과 BE의 요청 시 갱신을 지원한다. 사용자는 GitHub 앱의 만료 옵션을 활성화했다. 저장소 초기 동기화, 별도 계정 재연동 API, 대시보드·프로필 API는 이번 범위에 포함하지 않는다.

## 결정

- 공개 경로는 `/api` 아래 login, callback, refresh, logout, `/me` 다섯 개다. callback 성공은 `/home`, 실패는 code/token을 제거한 `/login?error=<safe_reason>`으로 302한다.
- GitHub OAuth App의 만료형 access/refresh token과 `read:user`만 사용한다. 앱의 Optional features에서 만료 옵션을 활성화하며 `offline_access` scope는 추가하지 않는다. 새 로그인 응답은 비어 있지 않은 access/refresh token, 유효한 `expires_in`·`refresh_token_expires_in`, `token_type=bearer`, `read:user` scope를 모두 요구한다. 누락·잘못된 응답은 `provider_unavailable`로 거부하고 저장하지 않는다. 로그인마다 browser-bound, single-use Redis state(`auth:oauth:{state}`, TTL 600초)와 S256 PKCE를 검증하고, code 교환으로 받은 access token의 `/user` 응답으로 사용자를 확인한다.
- GitHub access/refresh token은 별도 base64 32-byte key로 AES-GCM 암호화해 `github_accounts.access_token_encrypted BYTEA`, `refresh_token_encrypted BYTEA`에 저장한다. 응답 TTL로 UTC `token_expires_at`, `refresh_token_expires_at`을 계산한다. `token_type` 컬럼은 두지 않는다. 세 신규 필드는 모두 NULL인 기존 비만료 token 또는 모두 값이 있는 만료형 pair만 허용하는 CHECK를 둔다.
- GitHub API 호출은 BE의 `app.state.github.get(user_id, path)`를 사용한다. access 만료까지 60초 이하이면 요청 시 refresh하고, 새 access/refresh token과 두 만료 시각을 함께 저장한다. 기존 비만료 token은 유효한 동안 그대로 사용하며 다음 GitHub 로그인에서 만료형 pair로 교체한다. token을 FE나 DEVON JWT payload에 노출하지 않는다.
- callback 저장과 GitHub refresh는 같은 `github_accounts` row를 PostgreSQL `FOR UPDATE`로 잠그고 최신 pair를 다시 확인한다. 동시 요청은 앞선 갱신 결과를 재사용하며, 교체 전 access token으로 보낸 요청의 늦은 401이 새 pair를 폐기하지 않도록 현재 저장값을 확인한다. 원격 GitHub token rotation과 로컬 DB commit은 하나의 원자적 트랜잭션이 아니며 정확히 한 번의 갱신을 보장하지 않는다. 원격 갱신 후 DB 저장 전 장애가 나면 재로그인이 필요할 수 있다.
- refresh가 만료돼도 access가 아직 유효하면 남은 수명 동안 사용한다. access까지 만료돼 갱신할 수 없거나 GitHub가 refresh를 거부하면 `token_status=revoked`를 commit한 뒤 `token_invalid`로 처리한다. 현재 access token에 대한 GitHub API 401도 같은 폐기 기준을 적용한다. 네트워크 오류·429·5xx·잘못된 응답은 `provider_unavailable` 503으로 구분하고 기존 pair를 폐기하지 않는다. GitHub token 폐기는 DEVON JWT나 `auth_sessions`를 폐기하지 않는다.
- `/api/me`는 DB만 읽는다. GitHub account가 있고 `token_status=valid`이며 access 또는 refresh 중 하나가 아직 사용 가능하면 `githubLinked=true`다. 세 신규 필드가 모두 NULL인 기존 비만료 token도 valid 상태이면 true다. 조회 중 GitHub API 호출·token 갱신·폐기 쓰기는 하지 않는다.
- DEVON access/refresh token은 고정 HS256, issuer, audience, type과 `sub`(user UUID), `iat`, `exp`, `jti`를 가진 JWT다. refresh에는 `sid`, `generation`이 추가된다. 수명은 access 900초, refresh 1,209,600초다.
- JWT는 HttpOnly, SameSite=Lax cookie로만 전달한다. `accessToken` Path=/, `refreshToken` Path=/api/auth, `oauthState` Path=/api/auth/github이며 Domain은 설정하지 않는다. Secure는 production에서 true다.
- PostgreSQL만 Refresh 유효·폐기 기록의 원본이다. `users.refresh_generation`과 로그인별 `auth_sessions`의 현재 `refresh_jti`, 만료 시각을 저장하며 raw JWT는 저장하지 않는다. Redis와 이중 기록하거나 Redis로 fallback하지 않는다.
- 발급·갱신·로그아웃은 같은 사용자의 `users` row를 먼저 `FOR UPDATE`로 잠근 뒤 session을 처리한다. 갱신은 현재 generation, session 소유자·만료와 `jti`를 확인하고 한 DB 트랜잭션에서 `jti`와 14일 만료를 교체한다.
- 유효한 같은 generation/session에서 이전 `jti` 재사용이 감지되면 user generation을 새 UUID로 바꿔 사용자의 기존 모든 Refresh를 무효화한다. 이 변경을 commit한 뒤 401을 반환한다. 이미 폐기된 generation, 누락·만료 session은 갱신만 거부하며 새 로그인이나 다른 session을 폐기하지 않고 기록도 재생성하지 않는다.
- logout은 해당 `sid`·사용자·generation의 DB row만 삭제한다. 직전 갱신으로 `jti`가 바뀌어도 같은 로그인은 폐기한다. refresh cookie가 없거나 검증에 실패하면 쿠키 삭제만 멱등 수행한다. 유효한 토큰에 대한 DB 처리 장애는 503이며 폐기 성공으로 응답하거나 쿠키를 지우지 않는다.
- access 인증은 DB account status를 확인하되 Refresh session이나 Redis를 조회하지 않는다. logout·Refresh 전체 폐기 후에도 이미 발급한 Access JWT는 최대 15분간 유효하다. Redis 장애는 새 OAuth 시작·완료에 영향을 주지만 기존 로그인 갱신·로그아웃에는 영향을 주지 않는다.
- refresh/logout은 정확한 `FRONTEND_ORIGIN` Origin만 허용한다. error body는 항상 `{error:{reason,message,details:{}}}`이고 실제 HTTP status를 유지한다.
- local/dev는 GitHub Client ID와 secret이 둘 다 없을 때만 auth 외 기동을 허용하고 login은 503으로 응답한다. 둘 중 하나만 설정한 구성과 production의 credential 누락은 시작 시 거부한다.
- 초기 동기화 enqueue와 `/auth/github/link*`는 이번 callback에 포함하지 않는다.
- GitHub token 갱신용 공개 경로·cron·worker를 추가하지 않는다. `app.state.github.get`은 후속 GitHub API에서 사용할 서비스이며 저장소 수집·분석 pipeline 연결은 아직 골격이다.

GitHub token 응답, refresh 요청, rotation과 만료 규칙의 근거는 [GitHub 공식 OAuth App 인증 문서](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)다.

## 선택 근거

현재 Access·Refresh 인증은 이미 PostgreSQL에서 사용자 상태를 확인하고 있으며 별도 인증 저장소가 필요한 성능 병목은 확인되지 않았다. 로그인 유지 기록을 기존 DB에 두면 트랜잭션과 기존 백업·복구 절차를 활용할 수 있고, Redis에 인증 원본의 보존·복구 책임까지 추가하지 않아도 된다. DB 조회와 만료 row 정리 비용은 수용하며 실제 부하를 측정하기 전에는 저장소를 이원화하지 않는다. Redis는 OAuth state 같은 단기 상태와 향후 큐·캐시 역할로 남긴다.

## 이관과 정리

- Alembic `0001`의 사용자·GitHub 계정은 보존하고 `0002`에서 `users.refresh_generation UUID NOT NULL`을 무작위 값으로 채운 뒤 `auth_sessions`를 추가한다. 다른 도메인 테이블은 이번 변경 범위가 아니다.
- 구버전 인증 요청을 중지·종료한 뒤 migration과 신버전 시작을 진행한다. Redis 원본 버전과 DB 원본 버전을 동시에 서비스하지 않는다.
- 이전 `auth:refresh:*` Redis 기록은 읽거나 DB로 복사하지 않는다. 전환 전 로그인은 Access 만료 후 다음 Refresh 요청에서 재로그인이 필요하다. 이전 Redis 키는 TTL로 자연 만료시키며 일괄 삭제하지 않는다.
- `0002` downgrade는 DB Refresh 기록을 제거하므로 재로그인이 필요하다. 아직 살아 있는 Redis 키를 다시 읽는 구버전 기동이나 이전 Redis 상태 복원을 롤백 전략으로 사용하지 않는다.
- `python -m scripts.cleanup_auth_sessions`는 현재 UTC 기준 만료된 DB session만 삭제한다. 미만료 row는 보존하고 반복 실행해도 안전하다. 기존 배포 스케줄러에서 정기 실행하며 API 프로세스마다 별도 정리 작업을 띄우지 않는다. 상세 실행·복구 절차는 [배포 가이드](../../../backend/docs/deploy.md)를 따른다.
- GitHub token 전환은 별도 Alembic `0003`으로 처리한다. 서버를 중지하고 진행 중인 인증·GitHub 요청을 종료한 뒤 `alembic upgrade head`를 적용하고 새 서버를 시작한다. 기존 사용자·암호화 access token·DEVON session은 보존한다. 추가한 만료 시각 두 개와 암호화 refresh token은 기존 row에서 모두 NULL이며, 새 로그인 완료 시 전체 pair를 교체한다.
- `0003` downgrade는 만료형 계정의 `token_status`를 `revoked`로 변경한 뒤 세 신규 필드와 CHECK를 제거한다. 비만료 token을 생성하거나 복구하지 않는다. 기존 비만료 계정과 DEVON session은 보존하지만, 만료형 계정은 되돌린 서버가 지원하는 GitHub 앱 설정과 재로그인이 필요하다.

## 영향

정확한 wire shape는 [OpenAPI](../contracts/openapi.yaml), DB column은 [backend DB 문서](../../../backend/docs/db-schema.md), Redis key는 [backend Redis 문서](../../../backend/docs/redis-keys.md)를 따른다. FE는 token을 읽지 않고 인증 오류의 HTTP status와 reason을 함께 보존한다. GitHub App/환경 변수 설정은 [backend README](../../../backend/README.md)에 둔다.

## 대체 관계

[0001 공통 계약 이관](0001-contract-migration.md)의 인증 전달 `PENDING_FE`를 이 결정이 대체한다. WS 식별자, 면접 복구, report score 등 다른 보류는 변경하지 않는다.

2026-09-14에는 Redis generation/session 기록과 `auth_sessions` 미생성을 채택했다. 이 중 Refresh 저장소와 DB 제외 결정만 2026-09-15 사용자 승인으로 위 PostgreSQL 방식이 대체한다. JWT·쿠키·유효기간·공개 API·FE 갱신 정책은 그대로 유지한다.

2026-09-17 사용자 승인으로 GitHub non-expiring token 전제, 만료형 응답 거부, refresh·만료 컬럼 제외 결정을 위 만료형 pair와 서버 갱신 방식이 대체한다. DEVON JWT·쿠키·session 정책, GitHub `read:user` scope와 공개 API 경로는 유지한다.
