# auth

상태: 초안 — frontend/md/features/auth.md에서 이관.

현재 인증 기준은 [0003 서버 세션 결정](../../shared/decisions/0003-sprint1-session-auth.md)이다. Sprint 1은 기존 Redis와 `devon_session` 쿠키를 사용하며 JWT·refresh는 Sprint 2로 보류한다. 아래 요구사항의 정리는 실제 인증 구현 완료를 뜻하지 않는다.

## 목표 + 화면 구성

GitHub OAuth 단일 로그인. 아이디/비밀번호 가입은 없다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 로그인 | — | 서비스 소개 + `GitHub으로 로그인` 버튼 1개 |
| 로그인·재연동 실패 | — | 로그인 화면에 허용된 `?error=<표시 코드>`의 고정 안내; 검증된 재연동 실패는 `flow=link` |
| GitHub 재연동 안내 | — | 독립 화면 아님. 홈·분석 실패 화면에 배너로 노출 |

로그인 화면에 입력 폼은 없다. 버튼 하나뿐이다.

## 화면 이동 순서

```
/login
  └─ [GitHub으로 로그인] → window.location = '/auth/github/login'
       └─ GitHub 동의 화면
            ├─ 동의    → 서버 /auth/github/callback → 302 /home
            └─ 실패    → 302 /login?error=<표시 코드> (동의 거부는 denied)

(전역) 401 unauthenticated → queryClient.clear() → /login (refresh 재시도 없음)

(마이페이지) [로그아웃] → 확인 모달 → POST /auth/logout → /login

(GitHub 토큰 무효) 배너 [재연동] → window.location = '/auth/github/link'
       └─ GitHub 동의 → 서버 /auth/github/callback → 302 /home
            └─ 검증된 재연동 실패 → /login?error=<표시 코드>&flow=link
                 └─ [GitHub 재연동] → /api/auth/github/link
```

## API 연동

| # | 엔드포인트 | 호출 위치 | 방식 |
| --- | --- | --- | --- |
| 1 | `GET /auth/github/login` | 로그인 화면 버튼 | `window.location` — `shared/api.ts` 제외 |
| 2 | `GET /auth/github/callback` | 없음 | 로그인·재연동 공통 서버 302; 실패 안내는 로그인 화면 |
| 3 | `POST /auth/refresh` | Sprint 2 예약 | Sprint 1에서는 호출하지 않음 |
| 4 | `POST /auth/logout` | 마이페이지 로그아웃 | `fetch` |
| 5 | `GET /me` | 인증 가드 | `fetch` · `['me']` |
| 7 | `GET /auth/github/link` | 재연동 배너 | `window.location` — `shared/api.ts` 제외 |
| 8 | `GET /auth/github/link/callback` | 없음 | 재연동 호환 경로; 현재 callback은 #2 공유. 성공 복귀 후 `me`·`home` 무효화 |

### 인증 저장 방식

로그인 세션은 기존 Redis의 `auth:sess:{sid}`에 저장하고 브라우저에는 세션 식별자만 HttpOnly 쿠키로 전달한다. 프론트는 쿠키를 직접 읽거나 저장하지 않는다. 면접 API의 `sessionId`와 로그인 세션 식별자는 별개다.

| 용도 | 쿠키명 | 만료 |
| --- | --- | --- |
| 로그인 세션 | `devon_session` | 14일 sliding (`1209600`초) |

쿠키는 `HttpOnly; SameSite=Lax; Path=/`이며 운영 HTTPS 환경에서 `Secure`를 사용한다. 유효한 인증 요청에서 서버가 Redis TTL과 HTTP 응답의 쿠키 만료를 함께 14일로 연장한다. 별도 refresh 토큰이나 FE 갱신 요청은 없다. REST·SSE·WS 모두 같은 쿠키로 인증한다.

모든 요청에 `credentials: 'include'`. DuckDNS + Caddy 단일 도메인 배포로 same-origin이므로 CORS 설정은 없다.

### 세션 만료와 401 처리

```
세션 쿠키 없음 · 세션 만료/유실/무효
  └─ 401 unauthenticated → queryClient.clear() → /login
```

- 조회(Query)와 변경 요청(Mutation)에 같은 처리를 적용한다.
- 401에 refresh나 원 요청 자동 재시도를 하지 않는다. 이미 `/login`이면 같은 화면으로 반복 이동하지 않는다.
- Redis 조회 장애는 만료·유실과 구분해 기존 서버 오류로 처리하며 `401 unauthenticated`로 바꾸지 않는다.
- 로그아웃은 현재 Redis 로그인 세션 삭제와 쿠키 만료 후 `204`다. 이미 만료된 세션에도 `204`를 반환하며 GitHub 토큰은 보존한다. 성공 시 FE 캐시를 비우고 `/login`으로 이동한다.

### 에러 reason 분기

다음 HTTP 상태는 일반 API 오류에 적용한다. 브라우저 callback은 아래 표시 코드 규약을 따른다.

| reason | 코드 | 처리 |
| --- | --- | --- |
| `unauthenticated` | 401 | 캐시 clear → `/login`, refresh 재시도 없음 |
| `account_suspended` | 403 | 정지 안내 |
| `account_withdrawn` | 403 | 재가입 불가 안내 |
| `github_token_invalid` | 403 | 재연동 배너 |

`/auth/github/link`는 브라우저 이동이므로 서버가 세션 만료·유실 시 `/login`으로 302한다.

### callback 실패 안내

공통 callback과 재연동 호환 callback은 알려진 실패에 `302 /login?error=<표시 코드>`를 반환한다. 허용 코드는 `denied`, `invalid_state`, `invalid_code`, `provider_unavailable`, `provider_configuration`, `github_already_linked`, `account_suspended`, `account_withdrawn`이다. 로그인 화면은 코드별 고정 안내를 표시한다. 등록되지 않은 값은 무시하며 오류 배너 없이 기본 GitHub 로그인 버튼을 표시한다. query나 공급자 원문을 그대로 렌더링하지 않는다. `provider_configuration`은 지원하지 않는 GitHub expiry·refresh 토큰 설정 안내이며 API reason은 `provider_unavailable`을 유지한다.

재연동 state 검증 후 현재 활성 사용자가 시작 사용자와 일치한 경우에만 재시도 가능한 `denied`·`invalid_code`·`provider_unavailable`·`provider_configuration`·`github_already_linked`에 `flow=link`를 붙인다. 이 조합의 버튼은 고정된 `/api/auth/github/link`, 그 외에는 `/api/auth/github/login`으로 이동한다. `flow`는 인증 근거가 아니며 임의의 재시도 URL을 받지 않는다. state 무효·사용자 불일치·정지·탈퇴는 일반 로그인 안내로 돌아간다. 재연동 세션 만료·유실은 `/login`으로 이동하며 새 세션을 만들지 않는다.

Redis·세션·DB·enqueue 등 내부 실패는 기존 `500 internal_error` JSON envelope로 남는다. state 일회 소비·PKCE, state 쿠키 정리, `no-store`·`no-referrer`도 유지한다. 세부 브라우저 계약은 [FE API 명세 #2·#8](../../../frontend/docs/api-spec.md#2-get-authgithubcallback)을 따른다.

## 상태 요구사항

서버 상태가 아닌 화면 내부 상태만 필요하다.

| 상태 | 용도 |
| --- | --- |
| 로그아웃 확인 모달 열림 여부 | 마이페이지 |
| callback 실패 안내·재시도 목적 | 허용된 `error`와 `flow=link` 조합으로 고정 안내·버튼 결정 |

구현 방식은 `frontend/docs/task-07-auth.md` 참고.

## 검증 시나리오

- GitHub 로그인 성공 → `/home` 이동
- GitHub 동의 거부 → `/login?error=denied` 배너 노출
- 알려진 callback 오류 → 안전한 고정 안내; 등록되지 않은 `error` 값은 무시하고 오류 배너 없이 `/api/auth/github/login` 버튼 표시
- 검증된 재연동 실패 → `flow=link`와 `/api/auth/github/link` 재시도; state 무효·사용자 불일치·정지·탈퇴에는 일반 로그인 버튼
- 재연동 세션 유실 → 새 로그인 세션 없이 `/login`; callback 내부 장애 → 기존 `500` JSON
- 유효한 로그인 세션 사용 시 Redis TTL과 HTTP 쿠키 만료를 함께 14일로 연장, FE의 refresh 호출 없음
- 쿠키 없음·세션 만료/유실 → 조회·변경 요청 모두 캐시 clear 후 `/login`
- Redis 장애 → 기존 서버 오류 처리, 세션 만료로 오인해 로그인 이동하지 않음
- `account_suspended` / `account_withdrawn` 안내 노출
- `github_token_invalid` → 재연동 배너 노출
- 로그아웃 확인 모달 → 로그아웃 → `/login`
- 로그아웃 후 이전 세션으로 인증 불가, 중복 로그아웃도 `204`, GitHub 토큰 보존

## Sprint 2 참고

이전 JWT안의 Access 15분·Refresh 14일, 자동 갱신·single-flight·로테이션은 Sprint 1 요구사항에서 제외한다. 기존안은 `frontend/docs/api-spec.md`의 과거안과 변경 이력에 보존하며 Sprint 2 착수 시 세부를 검토한다.
