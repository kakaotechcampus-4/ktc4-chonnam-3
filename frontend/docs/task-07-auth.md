# task-07 — auth 구현

> 선행: task-06
> 근거: `spec/frontend/features/auth.md`

## 목표

GitHub OAuth 로그인 화면, cookie 인증 복구, `/me` guard, 로그아웃을 구현한다. link/initial sync/dashboard/profile API는 이 작업 범위가 아니다.

## 작업

- 로그인 화면 (버튼 1개, 폼 없음)
- `?error=denied` 배너
- `shared/api.ts` 공통 래퍼에 인증 복구 추가
  - access 누락 또는 `access_token_expired`: `POST /auth/refresh` 성공 시 원 요청 1회 재시도
  - `access_token_invalid`와 blocked account만 terminal auth 무효화. network/503은 cache를 보존하고 retry 제공
  - 같은 tab single-flight + Web Lock `devon-auth`; lock 안에서 raw `/me` 재확인
  - Web Locks 미지원 브라우저는 동시 refresh 대신 재로그인
  - `/auth/refresh` 자신은 인터셉터 제외
- logout epoch/cancellation으로 오래된 in-flight 요청의 cache 복원 차단
- `/me` 기반 인증 가드 라우트
- 로그아웃 확인 모달
- `account_suspended` / `account_withdrawn` 안내 화면
- Refresh 원본이 PostgreSQL로 변경되어도 token을 FE에서 읽거나 저장하지 않고 기존 API/cookie/lock 흐름을 유지한다.
- 전환 전 로그인은 다음 Refresh의 401에 따라 재로그인한다. DB 장애의 503은 인증 거부와 구분하고 캐시·로그인 상태를 보존한다. Redis는 OAuth state에만 필요하며 기존 Refresh/로그아웃을 막지 않는다.

## 완료 조건

- [ ] 로그인 화면
- [ ] `?error=denied` 배너
- [ ] `shared/api.ts` 공통 래퍼
- [ ] 401 인터셉터 + single-flight
- [ ] 인증 가드 (`/me` 기반 라우트 보호)
- [ ] 로그아웃 확인 모달
- [ ] `account_suspended` / `account_withdrawn` 안내 화면
- [ ] 전환 전 Refresh 거부와 DB 503의 재로그인/재시도 분기 구분
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add github oauth login flow and auth interceptor
```
