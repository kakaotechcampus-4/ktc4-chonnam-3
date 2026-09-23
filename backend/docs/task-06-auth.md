# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 근거: `spec/backend/architecture.md`

## 목표

GitHub OAuth 로그인과 Redis 기반 DEVON 로그인 세션을 구현한다. [공통 0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따른 코드와 아래 자동 검증을 반영했다. 실제 GitHub 계정의 로컬 로그인·세션·저장소 수집도 확인했으며 운영 배포는 수행하지 않았다. 실행 설정은 [로컬 OAuth 안내](local-oauth.md)를 따른다.

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

## 구현 반영

- GitHub 등록 callback은 로그인·재연동 공통 `http://localhost:5173/auth/github/callback` 하나다. Vite/Caddy가 `/api/auth/github/callback`으로 전달하며 코드 교환에는 공개 URI를 보낸다. legacy `/auth/github/link/callback`은 연동 state만 허용하는 호환 경로다.
- Redis OAuth state는 10분 TTL, 브라우저 쿠키 대조, 원자적 일회 소비, login/link 목적·연동 사용자 바인딩과 PKCE S256을 적용한다. 연동 도중 세션이 사라지면 새 로그인을 만들지 않고 `/login`으로 이동한다.
- GitHub의 immutable 사용자 ID로 기존 사용자를 찾고 동시 최초 로그인에서 유니크 제약으로 중복 사용자 생성을 막는다. 재연동으로 GitHub 계정을 교체할 수 없다. provider 호출 도중 계정 상태가 바뀌어도 DB를 다시 읽어 정지·탈퇴를 확인한다.
- `HTTPConnection` 기반 공통 dependency와 ASGI 응답 middleware가 REST·SSE·WS handshake 인증·쿠키 연장을 담당한다. Redis expiry 갱신은 삭제된 세션을 다시 만들지 않는다.
- OAuth App의 **Expire user access tokens는 OFF**, `offline_access` 요청은 제외한다. refresh·expiry 필드가 포함된 provider 응답은 저장하지 않는다.
- `initial_sync`는 계정 commit 후 DB job ID만 큐에 넣고 별도 ARQ worker가 public 저장소 목록 메타데이터를 수집한다. GitHub 토큰은 Redis job 인자에 넣지 않는다. AI 분석·면접·리포트 생성은 이번 범위에 포함하지 않는다.

## 검증 기록과 운영 범위

2026-09-23 최종 검증은 다음과 같다.

- BE 전체 pytest **128개 통과**. 실제 격리 PostgreSQL·Redis를 사용하며 GitHub HTTP는 대체한다. state·PKCE·동시 로그인·세션 연장·로그아웃·초기 수집 복구와 실제 Uvicorn 오류 로그의 비밀값 제외를 포함한다. 만료형 GitHub 토큰 응답은 연결 장애와 다른 설정 불일치 메시지로 구분하며 토큰 값이 로그에 노출되지 않음을 검증한다.
- FE MSW 기반 Playwright **9개 통과**, 실제 Vite→FastAPI→PostgreSQL/Redis 및 브라우저 쿠키 통합 테스트 **1개 통과**. 단일 callback 로그인·재연동·새로고침·재사용 거부·로그아웃을 확인한다.
- BE Ruff 검사·포맷 검사, mypy(116개 소스), FE lint·TypeScript·production build 통과. `uv lock --check`, 공통 계약 검사(스키마 2개·부분 OpenAPI·fixture 7개), `git diff --check` 통과.

브라우저 통합 테스트는 GitHub 동의 화면·토큰·사용자 HTTP 응답을 대체하므로 실제 GitHub 계정 동의나 운영 배포 성공을 뜻하지 않는다. 재실행 방법은 [FE 안내](../../frontend/README.md)의 `npm run test:integration`을 따른다.

별도로 사용자가 실제 브라우저에서 GitHub 로그인을 완료하고 홈 진입을 확인했다. 최초 실패는 GitHub가 반환한 만료·refresh 필드와 현재 long-lived 모델의 불일치였다. OAuth App의 **Expire user access tokens를 OFF**로 저장한 뒤 새 로그인에서 해당 필드가 없는 토큰 교환과 사용자 조회의 HTTP 200을 확인했다. 토큰은 암호화 저장됐고, 일반 `app.main:app`으로 임시 진단 서버를 교체한 뒤에도 Redis 세션, 인증된 `/api/me`·홈 조회 200, 비로그인 `/api/me` 401, 14일 쿠키 갱신과 `HttpOnly`·`SameSite=Lax`·`Path=/`를 확인했다. 실제 ARQ worker의 초기 수집이 성공해 공개 저장소 29개가 저장됐고 비공개 저장소는 0개였다. 기존 DB는 보존하고 별도 로컬 DB에서 검증했다.

새 격리 DB에서 migration upgrade·스키마 비교·downgrade·재upgrade를 검증했고 Caddy validate와 Compose config 검증을 실행했다. 실제 배포 컨테이너 구동과 기존 운영 DB migration은 수행하지 않았다.

fixture는 `_test` 이름의 `TEST_DATABASE_URL`과 Redis DB 13·14·15의 `TEST_REDIS_URL`만 허용하며 대상 테스트 데이터를 초기화한다. 기존 ignored PostgreSQL 55432의 이전 `0002`·`0003` migration 이력에는 자동 적용하지 않았다. 새 DB 또는 검토한 이력에서 migration을 실행한다.

## 완료 조건

- GitHub token 평문이 응답/log/DB에 남지 않는다.
- 로그인·연동 요청에 `read:user`가 적용되고, public 저장소 수집에 불필요한 `repo`·`public_repo` scope를 추가하지 않는지 검증한다. 실제 부여된 권한은 기존 `token_scope`에 기록하며 private 저장소 제외를 유지한다.
- GitHub refresh token/expiry 컬럼과 SQL `auth_sessions` 없이 기존 계정 스키마를 유지한다.
- suspended/withdrawn 사용자는 로그인 차단 reason을 반환한다.
- 세션 발급·조회·쿠키/Redis의 14일 sliding 갱신·유실/만료 시 재로그인·Redis 장애 구분, REST·SSE·WS 인증, 멱등 로그아웃을 검증한다.
