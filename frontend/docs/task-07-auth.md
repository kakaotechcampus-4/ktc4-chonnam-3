# task-07 — auth 구현

> 선행: task-06
> 근거: `spec/frontend/features/auth.md`

## 목표

GitHub OAuth 로그인 화면, 401 인터셉터, 재연동 배너, 로그아웃을 구현한다.

## 작업

- 로그인 화면 (버튼 1개, 폼 없음)
- `?error=denied` 배너
- `shared/api.ts` 공통 래퍼에 401 인터셉터 추가
  - `access_token_expired`: `POST /auth/refresh` 성공 시 원 요청 1회 재시도, 실패 시 `queryClient.clear()` → `/login`
  - 그 외 reason: `queryClient.clear()` → `/login`
  - single-flight: `refreshPromise`는 React state로 두지 않고 `shared/api.ts` 모듈 스코프 변수로 유지한다 (인터셉터가 렌더 사이클 밖에서 접근해야 함)
  - `/auth/refresh` 자신은 인터셉터 제외
- `/me` 기반 인증 가드 라우트
- GitHub 재연동 배너 컴포넌트 (홈·분석 실패 화면 공용)
- 로그아웃 확인 모달
- `account_suspended` / `account_withdrawn` 안내 화면

## 완료 조건

- [ ] 로그인 화면
- [ ] `?error=denied` 배너
- [ ] `shared/api.ts` 공통 래퍼
- [ ] 401 인터셉터 + single-flight
- [ ] 인증 가드 (`/me` 기반 라우트 보호)
- [ ] GitHub 재연동 배너 컴포넌트 (홈·분석 실패 공용)
- [ ] 로그아웃 확인 모달
- [ ] `account_suspended` / `account_withdrawn` 안내 화면
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add github oauth login flow and auth interceptor
```
