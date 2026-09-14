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

`QueryCache`의 `onError`에서 처리한다. 화면마다 개별 처리하지 않는다.

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
- [ ] 401 응답 시 로그인 화면으로 이동
- [ ] `npm run build` 통과

## 커밋

```
feat: add tanstack query setup and query keys
```