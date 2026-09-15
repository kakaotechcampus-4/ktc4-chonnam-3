# auth

상태: Sprint 1 FIX. 공통 원본은 `spec/shared/contracts/openapi.yaml`과 `spec/shared/decisions/0002-github-oauth.md`다.

## 목표 + 화면 구성

GitHub OAuth 단일 로그인. 아이디/비밀번호 가입은 없다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 로그인 | — | 서비스 소개 + `GitHub으로 로그인` 버튼 1개 |
| 로그인 실패 | — | 로그인 화면에 `?error=denied` 배너 |
| GitHub 재연동 안내 | — | 독립 화면 아님. 홈·분석 실패 화면에 배너로 노출 |

로그인 화면에 입력 폼은 없다. 버튼 하나뿐이다.

## 화면 이동 순서

```
/login (anonymous-safe /api/me probe)
  └─ [GitHub으로 로그인] → window.location = '/api/auth/github/login'
       └─ GitHub 동의 화면
            ├─ 동의    → 서버 /auth/github/callback → 302 /home
            └─ 거부    → 302 /login?error=denied

(전역) access 누락 또는 access_token_expired → POST /api/auth/refresh
                                   ├─ 성공 → 원 요청 재시도 (화면 유지)
                                   └─ 인증 거부(401 또는 정지·탈퇴) → queryClient.clear() → /login

(마이페이지) [로그아웃] → 확인 모달 → POST /api/auth/logout → /login
```

## API 연동

| # | 엔드포인트 | 호출 위치 | 방식 |
| --- | --- | --- | --- |
| 1 | `GET /api/auth/github/login` | 로그인 화면 버튼 | `window.location` — API wrapper 제외 |
| 2 | `GET /api/auth/github/callback` | 없음 | 서버가 302. 프론트 무관 |
| 3 | `POST /api/auth/refresh` | 인증 복구 내부 | `fetch`. queryKey 없음 |
| 4 | `POST /api/auth/logout` | 마이페이지 로그아웃 | `fetch` |
| 5 | `GET /api/me` | 인증 가드 | `fetch` · `['me']` |

### 인증 저장 방식

JWT를 HttpOnly 쿠키로 전달한다. 프론트는 토큰을 직접 읽거나 저장하지 않는다.

| 토큰 | 쿠키명 | 만료 | Path |
| --- | --- | --- | --- |
| Access | `accessToken` | 15분 | `/` |
| Refresh | `refreshToken` | 14일 | `/api/auth` |
| OAuth state | `oauthState` | 10분 | `/api/auth/github` |

모든 요청에 `credentials: 'include'`. DuckDNS + Caddy 단일 도메인 배포로 same-origin이므로 CORS 설정은 없다.

Refresh 유효·폐기 기록은 PostgreSQL `users.refresh_generation`과 `auth_sessions`에서 관리한다. Redis는 OAuth state에만 쓰며 기존 session의 갱신·로그아웃은 Redis에 의존하지 않는다. FE가 DB 저장 방식에 맞춰 token을 읽거나 새 필드를 추가할 필요는 없다. logout 후 이미 발급된 Access JWT는 최대 15분간 유효하다.

2026-09-15 저장소 전환 전 로그인은 다음 Refresh에서 401로 거부되어 재로그인한다. FE는 기존 확정된 인증 실패 처리로 대응하며 예전 Refresh를 계속 재시도하지 않는다.

### 인증 복구 정책

```
GET /me 또는 보호 요청
├─ access cookie 누락(unauthenticated) 또는 access_token_expired
│   ├─ Web Lock `devon-auth` 획득
│   ├─ lock 안에서 raw /me 재확인
│   ├─ 다른 tab이 이미 복구했으면 원 요청 재시도
│   ├─ 아니면 POST /auth/refresh (single-flight)
│   ├─ 성공 → 원 요청 1회 재시도
│   └─ 인증 거부(401 또는 정지·탈퇴) → queryClient.clear() → /login
├─ access_token_invalid 또는 blocked account → auth cache 무효화
└─ network/503 → 기존 auth 상태 유지 + retry 노출
```

- 재시도는 1회만
- 같은 tab은 single-flight, tab 사이는 Web Locks API의 `devon-auth` lock으로 직렬화한다.
- Web Locks API가 없는 브라우저는 안전하지 않은 동시 refresh 대신 재로그인을 요구한다.
- logout epoch/cancellation 이후 완료된 요청은 auth cache를 복원하지 못한다.
- `/auth/refresh` 자신은 인터셉터 제외

### 에러 reason 분기

| reason | 코드 | 처리 |
| --- | --- | --- |
| `unauthenticated` | 401 | `/login` |
| `access_token_expired` | 401 | 갱신 후 재시도 |
| `access_token_invalid` | 401 | clear → `/login` |
| `refresh_token_invalid` | 401 | clear → `/login` |
| `account_suspended` | 403 | 정지 안내 |
| `account_withdrawn` | 403 | 재가입 불가 안내 |
| `invalid_state` / `invalid_code` | 400 | 로그인 재시도 안내 |
| `invalid_origin` | 403 | 요청 중단 후 로그인 상태 확인 |
| `provider_unavailable` | OAuth redirect | GitHub 장애 안내 |
| `service_unavailable` | 503 | auth 상태 유지, 재시도 |
| `internal_error` | 500 | auth 상태 유지, 재시도 |

refresh/logout 요청은 브라우저가 설정하는 정확한 Origin을 사용한다. 초기 동기화와 GitHub 재연동 API는 이번 범위가 아니다.

## 상태 요구사항

서버 상태가 아닌 화면 내부 상태만 필요하다.

| 상태 | 용도 |
| --- | --- |
| 로그아웃 확인 모달 열림 여부 | 마이페이지 |
| `?error=denied` 배너 표시 여부 | 로그인 화면 쿼리 파싱 |
| refresh single-flight 보장 | 401 인터셉터 — 렌더 사이클과 무관하게 유지되어야 함 |

구현 방식은 `frontend/docs/task-07-auth.md` 참고.

## 검증 시나리오

- GitHub 로그인 성공 → `/home` 이동
- GitHub 동의 거부 → `/login?error=denied` 배너 노출
- `access_token_expired` → 자동 갱신 후 원 요청 재시도, 화면 안 끊김
- refresh 인증 거부(401 또는 정지·탈퇴) → 캐시 clear 후 `/login`; network/503은 cache 보존
- `account_suspended` / `account_withdrawn` 안내 노출
- 로그아웃 확인 모달 → 로그아웃 → `/login`
- network/503에서 auth cache 유지와 retry 노출
- DB 저장소 전환 전 Refresh 거부 시 무한 재시도 없이 재로그인; Redis 장애만으로 기존 갱신·로그아웃이 실패하지 않음
- multi-tab refresh/logout이 `devon-auth` lock으로 직렬화되고 logout 뒤 stale request가 cache를 복원하지 않음
