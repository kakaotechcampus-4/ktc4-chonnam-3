# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 근거: `spec/backend/architecture.md`

## 목표

GitHub OAuth 로그인과 DEVON 자체 인증 토큰 발급 기반을 구현한다.

## 작업

- GitHub OAuth callback에서 GitHub access token을 받고 FE에는 노출하지 않는다.
- GitHub token은 암호화해 `github_accounts.access_token_encrypted`에 저장한다.
- GitHub OAuth App long-lived access token을 전제로 한다.
- `github_accounts` token field는 `access_token_encrypted`, `token_status`, `token_scope`만 둔다.
- `token_type`, `token_expires_at`, `refresh_token_encrypted`, `refresh_token_expires_at`는 만들지 않는다.
- GitHub API 호출은 BE가 대행한다.
- DEVON 자체 JWT를 생성해 이후 BE API 인증에 사용한다.
- DEVON JWT payload에는 GitHub access token을 넣지 않는다.
- DEVON JWT 생성은 `users.id`와 필요 시 `github_accounts.id` 같은 식별자만 사용한다.
- JWT 전달 방식은 `PENDING_FE`이므로 cookie/body 세부 구현은 결정값이 들어오기 전까지 확장 가능한 구조로 둔다.
- 로그인 성공 후 `initial_sync` job을 enqueue한다.
- private repo scope는 요청하지 않는다.

## 완료 조건

- GitHub token 평문이 응답/log/DB에 남지 않는다.
- public repo 접근에 필요한 최소 scope만 사용한다.
- refresh token/expiry 컬럼 없이 migration이 작성된다.
- suspended/withdrawn 사용자는 로그인 차단 reason을 반환한다.
