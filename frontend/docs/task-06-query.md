# 작업 06 — TanStack Query 설정

> 선행: task-05 완료

## 목표

Query 전역 설정, queryKey 정의, 401 전역 처리를 구성한다.

## 1. 설치

```bash
npm i @tanstack/react-query
```

## 2. queryKeys

`src/shared/queryKeys.ts`

```ts
export const queryKeys = {
  me: ['me'] as const,
  home: ['home'] as const,
  interviews: (page: number) => ['interviews', { page }] as const,
  analysisRun: (runId: string) => ['analysis-run', runId] as const,
  analysisResult: (runId: string) => ['analysis-run', runId, 'result'] as const,
  interview: (id: string) => ['interview', id] as const,
  report: (id: string) => ['interview', id, 'report'] as const,
};
```

키를 문자열로 직접 쓰지 않고 이 파일을 통해 참조한다. 오타가 나면 캐시가 조용히 어긋나 "화면이 갱신되지 않는" 버그가 된다.

계층 구조라 `['interview', id]` 무효화 시 하위 `report`까지 함께 무효화된다.

## 3. 전역 설정

`src/main.tsx` 또는 `src/providers.tsx`

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
});
```

## 4. 401 전역 처리

현재 로컬에는 조회 요청을 처리하는 `QueryCache.onError`만 있다. 아래 초기 예시에는 변경 요청 처리와 캐시 정리가 빠져 있으므로 구현 완료 기준으로 쓰지 않는다.

[0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 Query와 Mutation 모두 `401 unauthenticated`이면 사용자 캐시를 비우고 로그인으로 이동해야 한다. 인증 오류에는 위의 일반 `retry: 1`을 적용하지 않고 refresh·요청 재전송을 하지 않는다. Redis 장애는 로그인 만료가 아닌 서버 오류로 구분한다. 상세 보완·검증은 [task-07-auth](task-07-auth.md)를 따른다.

```ts
queryCache: new QueryCache({
  onError: (error) => {
    const err = error as ApiError;
    if (err?.error?.reason === 'unauthenticated') {
      window.location.href = '/login';
    }
  },
}),
```

`useNavigate`는 컴포넌트 밖에서 못 쓰므로 `window.location`을 쓴다.

## 완료 조건

- [ ] `QueryClientProvider`가 앱을 감싼다
- [ ] queryKeys가 모든 조회 엔드포인트를 커버
- [ ] Query·Mutation의 `401 unauthenticated`에서 캐시 정리 후 로그인 이동; refresh·인증 재시도 없음
- [ ] `npm run build` 통과

## 커밋

```
feat: add tanstack query setup and query keys
```
