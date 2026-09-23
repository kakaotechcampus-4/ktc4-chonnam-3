import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/types/api';

let leavingSession = false;

export function isSessionEnding() {
  return leavingSession;
}

export async function clearSessionQueries() {
  leavingSession = true;
  // 늦게 도착한 응답이 이전 사용자의 캐시를 되살리지 않도록 진행 중인 조회부터 취소한다.
  await queryClient.cancelQueries();
  queryClient.clear();
}

function handleAuthError(error: unknown) {
  if (!isApiError(error) || !('status' in error)) return;
  const reason = error.error.reason;
  const unauthenticated = error.status === 401 && reason === 'unauthenticated';
  const blocked =
    error.status === 403 && (reason === 'account_suspended' || reason === 'account_withdrawn');
  // 여러 요청이 동시에 실패해도 캐시 정리와 로그인 이동은 한 번만 수행한다.
  if ((!unauthenticated && !blocked) || leavingSession) return;

  leavingSession = true;
  void clearSessionQueries().then(() => {
    if (window.location.pathname !== '/login') {
      window.location.replace(blocked ? `/login?error=${reason}` : '/login');
    }
  });
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // 세션 종료 중이거나 인증·권한 오류이면 자동 재시도로 보호 API를 다시 호출하지 않는다.
        if (leavingSession) return false;
        if (
          isApiError(error) &&
          'status' in error &&
          (error.status === 401 || error.status === 403)
        ) {
          return false;
        }
        return failureCount < 1;
      },
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
  queryCache: new QueryCache({ onError: handleAuthError }),
  mutationCache: new MutationCache({ onError: handleAuthError }),
});
