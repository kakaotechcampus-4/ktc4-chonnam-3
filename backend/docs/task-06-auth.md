# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 근거: `spec/backend/architecture.md`

## 목표

GitHub OAuth 로그인과 Redis 기반 DEVON 로그인 세션을 구현한다. [공통 0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)은 확정된 설계이며 아래 실제 인증 기능은 구현·검증할 작업이다.

## 작업

- GitHub OAuth callback에서 GitHub access token을 받고 FE에는 노출하지 않는다.
- GitHub token은 암호화해 `github_accounts.access_token_encrypted`에 저장한다.
- GitHub OAuth App long-lived access token을 전제로 한다.
- `github_accounts` token field는 `access_token_encrypted`, `token_status`, `token_scope`만 둔다.
- `token_type`, `token_expires_at`, `refresh_token_encrypted`, `refresh_token_expires_at`는 만들지 않는다.
- GitHub API 호출은 BE가 대행한다.
- OAuth 성공 시 새 로그인 세션을 발급하고 Redis `auth:sess:{sid}`에 기존 사용자 식별자를 연결한다. 14일(1,209,600초) sliding 갱신은 Redis TTL과 HTTP 응답의 쿠키 만료가 함께 연장되도록 구현한다.
- 로그인 쿠키에는 세션 식별자만 전달하고 GitHub access token을 넣지 않는다.
- REST 요청·SSE 연결·WS handshake는 HttpOnly `devon_session` 쿠키를 사용한다. `Path=/`, `SameSite=Lax`, 운영 환경 `Secure`를 적용한다.
- 세션 유실·만료는 인증 실패로 처리하고 재로그인한다. Postgres에서 로그인 세션을 재구성하지 않는다.
- Redis 조회 장애는 세션 만료와 구분해 기존 공통 오류 계약의 서버 오류로 처리한다. 인증을 허용하거나 `401`로 바꾸지 않는다.
- 로그아웃은 현재 세션 삭제와 쿠키 만료로 처리한다. 이미 만료·삭제된 세션에도 `204`로 응답한다.
- SQL `auth_sessions`와 DEVON refresh token 저장 구조는 Sprint 1에 추가하지 않는다. JWT·refresh와 그 저장 설계는 Sprint 2로 넘긴다.
- 로그인 성공 후 `initial_sync` job을 enqueue한다.
- 로그인·연동 모두 기존 `read:user`를 사용한다. public 저장소 읽기만 수행하므로 `repo`·`public_repo` scope는 요청하지 않는다. 근거는 [GitHub OAuth scope 안내](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)다.

## 완료 조건

- GitHub token 평문이 응답/log/DB에 남지 않는다.
- 로그인·연동 요청에 `read:user`가 적용되고, public 저장소 수집에 불필요한 `repo`·`public_repo` scope를 추가하지 않는지 검증한다. 실제 부여된 권한은 기존 `token_scope`에 기록하며 private 저장소 제외를 유지한다.
- GitHub refresh token/expiry 컬럼과 SQL `auth_sessions` 없이 기존 계정 스키마를 유지한다.
- suspended/withdrawn 사용자는 로그인 차단 reason을 반환한다.
- 세션 발급·조회·쿠키/Redis의 14일 sliding 갱신·유실/만료 시 재로그인·Redis 장애 구분, REST·SSE·WS 인증, 멱등 로그아웃을 검증한다.
