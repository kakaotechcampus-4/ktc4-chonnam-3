# 서버 상태 관리 — TanStack Query 채택

- 상태: Accepted (기존 구현 반영 — frontend/decisions/tanstack-query.md에서 이관)
- 날짜: 미기입 — 확인 후 채움
- 관련 PR: 미기입 — 확인 후 채움
- 검토자: 미기입 — 확인 후 채움

## 맥락

서버 상태(캐싱·리페치·로딩/에러)를 관리할 방법이 필요했다. 전역 상태 라이브러리를 별도로 둘지, 서버 상태 전용 라이브러리로 충분한지 결정이 필요했다.

## 결정

서버 상태는 TanStack Query로 관리한다. 클라이언트 전용 상태(모달 열림, 입력 중 값 등)는 컴포넌트 로컬 state로 처리하고, Redux·Zustand 같은 별도 전역 상태 라이브러리는 두지 않는다.

## 이유

이 서비스의 상태 대부분은 서버 기원(폴링, 캐시 무효화, 401 공통 처리)이라 Query가 해결하는 문제와 겹친다. 로컬 UI 상태만 남으면 컴포넌트 state로 충분하고 전역 스토어가 필요 없다.

## 영향

- `src/providers.tsx`: `staleTime: 60_000`, `retry: 1`, `refetchOnWindowFocus: false`를 기본값으로 둔다.
- `QueryCache.onError`에서 `error.reason === 'unauthenticated'`면 `/login`으로 리다이렉트한다 (401 공통 처리, 화면별 개별 처리 금지).
- `src/shared/queryKeys.ts`에서 팩토리 함수로 쿼리 키를 관리한다. 문자열을 직접 쓰면 오타로 캐시가 조용히 어긋나는 버그가 된다.
- 실시간(WebSocket) 상태는 이 결정의 범위 밖이다 — `spec/frontend/features/interview.md`의 "상태 요구사항" 참고.

## 대체 관계

없음 (최초 결정).
