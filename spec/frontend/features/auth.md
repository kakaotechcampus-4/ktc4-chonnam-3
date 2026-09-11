# auth

상태: 초안 — frontend/md/features/auth.md에서 이관.

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
/login
  └─ [GitHub으로 로그인] → window.location = '/auth/github/login'
       └─ GitHub 동의 화면
            ├─ 동의    → 서버 /auth/github/callback → 302 /home
            └─ 거부    → 302 /login?error=denied

(전역) 401 access_token_expired → POST /auth/refresh
                                   ├─ 성공 → 원 요청 재시도 (화면 유지)
                                   └─ 실패 → queryClient.clear() → /login

(마이페이지) [로그아웃] → 확인 모달 → POST /auth/logout → /login

(GitHub 토큰 무효) 배너 [재연동] → window.location = '/auth/github/link'
       └─ GitHub 동의 → 서버 /auth/github/link/callback → 302 /home
```

## API 연동

| # | 엔드포인트 | 호출 위치 | 방식 |
| --- | --- | --- | --- |
| 1 | `GET /auth/github/login` | 로그인 화면 버튼 | `window.location` — `shared/api.ts` 제외 |
| 2 | `GET /auth/github/callback` | 없음 | 서버가 302. 프론트 무관 |
| 3 | `POST /auth/refresh` | 401 인터셉터 내부 | `fetch`. queryKey 없음 |
| 4 | `POST /auth/logout` | 마이페이지 로그아웃 | `fetch` |
| 5 | `GET /me` | 인증 가드 | `fetch` · `['me']` |
| 7 | `GET /auth/github/link` | 재연동 배너 | `window.location` — `shared/api.ts` 제외 |
| 8 | `GET /auth/github/link/callback` | 없음 | 서버가 302. 복귀 후 `me`·`home` 무효화 |

### 인증 저장 방식

JWT를 HttpOnly 쿠키로 전달한다. 프론트는 토큰을 직접 읽거나 저장하지 않는다.

| 토큰 | 쿠키명 | 만료 |
| --- | --- | --- |
| Access | `accessToken` | 15분 |
| Refresh | `refreshToken` | 14일 |

모든 요청에 `credentials: 'include'`. CloudFront 단일 배포로 same-origin이므로 CORS 설정은 없다.

### 401 인터셉터 정책

```
401 수신
├─ reason === 'access_token_expired'
│   ├─ 갱신 진행 중이면 → 그 Promise를 await (single-flight)
│   ├─ 아니면 → POST /auth/refresh
│   ├─ 성공 → 원 요청 1회 재시도
│   └─ 실패 → queryClient.clear() → /login
└─ 그 외 → queryClient.clear() → /login
```

- 재시도는 1회만
- 갱신은 single-flight — 동시에 여러 401이 발생해도 `/auth/refresh` 호출은 1회만 일어나야 한다 (로테이션 충돌 시 강제 로그아웃 발생)
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
| `github_token_invalid` | 403 | 재연동 배너 |
| `invalid_state` / `invalid_code` | 400 | 로그인 재시도 안내 |
| `provider_unavailable` | 502 | GitHub 장애 안내 |
| `github_already_linked` | 409 | 이미 연동됨 안내 |

`/auth/github/link`는 브라우저 이동이라 401 인터셉터를 타지 않는다. 서버가 만료 시 `/login`으로 302한다.

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
- refresh 실패 → 캐시 clear 후 `/login`
- `account_suspended` / `account_withdrawn` 안내 노출
- `github_token_invalid` → 재연동 배너 노출
- 로그아웃 확인 모달 → 로그아웃 → `/login`
