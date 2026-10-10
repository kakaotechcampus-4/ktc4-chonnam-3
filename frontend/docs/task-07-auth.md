# task-07 — auth 구현

> 선행: task-06
> 근거: `spec/frontend/features/auth.md`

## 목표

GitHub OAuth 로그인 화면, 서버 세션 인증과 공통 401 처리, 재연동 배너, 로그아웃을 구현한다. [0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 Sprint 1은 기존 Redis·`devon_session`이며 JWT·refresh는 Sprint 2로 보류한다.

FE는 `/me` 라우트 가드와 Query·Mutation 공통 인증 오류 처리를 사용한다. 세션 종료 시 조회를 취소하고 캐시를 비우며 이후 요청을 차단한 뒤 로그인 화면으로 이동한다. refresh 호출은 제거했고, MSW의 로그아웃은 모의 세션을 만료시킨다. `tests/auth.spec.ts`는 이 화면 흐름을 검증하며 실제 GitHub·Redis·쿠키 검증은 서버 통합 테스트와 구분한다.

## 작업

- 로그인 화면 (버튼 1개, 폼 없음)
- `?error=denied` 배너
- 기존 `credentials: 'include'`를 유지하고 REST·SSE·WS에서 같은 `devon_session` 쿠키로 인증
  - HttpOnly·`Path=/`·`SameSite=Lax`·운영 HTTPS `Secure`, Redis TTL과 HTTP 쿠키 만료의 14일 sliding 연장 연결 확인
- 조회·변경 요청의 공통 401 처리
  - `unauthenticated`: `queryClient.clear()` → `/login`; 로그인 화면 반복 이동 방지
  - 401에 refresh 호출·원 요청 자동 재시도 없음
  - Redis 조회 장애는 만료와 구분해 기존 서버 오류로 안내; 401·로그인 이동으로 바꾸지 않음
- 사용하지 않는 `api.refresh`, MSW `/auth/refresh`, 기존 smoke refresh 검사를 Sprint 1 동작에서 제거·분리
- MSW 인증 상태·만료·유실·로그아웃 시나리오를 실제 세션 계약에 맞춰 정리. 현재 항상 성공하는 응답을 인증 검증으로 취급하지 않음
- `/me` 기반 인증 가드 라우트
- GitHub 재연동 배너 컴포넌트 (홈·분석 실패 화면 공용)
- 로그아웃 확인 모달
- 로그아웃은 현재 Redis 로그인 세션 삭제·쿠키 만료 후 `204`, 만료 후 재호출도 `204`, GitHub 토큰 보존 확인
- `account_suspended` / `account_withdrawn` 안내 화면

## 완료 조건

아래는 검수 기준이며 현재 게시본의 통과 표가 아니다. 구현 범위·실행 결과·남은 작업은 [인증 구현 기록](../../spec/backend/implementation-auth.md)에 모은다.

- 로그인 화면과 `?error=denied` 배너
- `shared/api.ts` 공통 래퍼
- Query·Mutation의 401 캐시 정리·로그인 이동, refresh·401 자동 재시도 없음
- 세션 쿠키·14일 sliding·REST/SSE/WS 인증 연결 확인
- Redis 조회 장애를 세션 만료와 구분해 기존 서버 오류로 처리
- 기존 refresh API 함수·MSW 핸들러·smoke 검사 정리
- 인증 가드 (`/me` 기반 라우트 보호)
- GitHub 재연동 배너 컴포넌트 (홈·분석 실패 공용)
- 로그아웃 확인 모달
- 세션 만료·유실·로그아웃 후 인증 거절 및 중복 로그아웃 `204` 확인
- `account_suspended` / `account_withdrawn` 안내와 허용된 callback 오류 코드의 고정 문구 표시
- `npm run build`, `npm run lint` 및 인증 화면·서버 통합 검증

## 검증 범위

MSW 화면 테스트는 BE 수집 의존성과 별도로 실행할 수 있다. 실제 API·DB·Redis·브라우저 통합은 PR #57에서 분리한 #45 수집 구현과 보존한 보안 보완을 결합한 뒤 검증한다. 과거 통합본의 성공 기록을 현재 게시본의 통과 결과로 사용하지 않는다. 실행 방법은 [FE 안내](../README.md)를 따른다.

## 커밋

```
feat: add github oauth login flow and auth interceptor
```
