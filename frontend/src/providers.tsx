import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { isAuthFailure } from '@/shared/api';
import { subscribeAuthChanges } from '@/shared/authEvents';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => !isAuthFailure(error) && failureCount < 1,
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
});

subscribeAuthChanges(({ reason, redirect }) => {
  // 캐시를 비우기 전에 진행 중인 조회를 취소해 늦게 도착한 결과가 캐시를 다시 채우지 못하게 한다.
  void queryClient.cancelQueries().then(() => {
    if (!redirect) return;
    queryClient.clear();
    if (window.location.pathname === '/login') return;
    const blocked = reason === 'account_suspended' || reason === 'account_withdrawn';
    window.location.assign(`/login${blocked ? `?error=${reason}` : ''}`);
  });
});

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
