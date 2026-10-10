import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/shared/queryKeys';
import { isApiError } from '@/types/api';

// OAuth 로그인은 전체 페이지 이동으로 새 문서를 로드할 때 이 상태를 초기화한다.
// SPA 로그인으로 바꾸면 종료 상태의 초기화 정책도 함께 변경해야 한다.
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

// 토큰 무효는 /me의 githubLinked를 false로 바꾼다. staleTime을 기다리지 않고 헤더 배지를 갱신한다.
// ['me'] 접두사라 /me/profile도 함께 갱신된다.
export function refreshMeIfTokenInvalid(reason: string | null | undefined) {
  if (reason === 'github_token_invalid') {
    void queryClient.invalidateQueries({ queryKey: queryKeys.me });
  }
}

function handleAuthError(error: unknown) {
  if (!isApiError(error)) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    // 예외 이름·메시지·스택에 응답 원문이 섞일 수 있어 고정된 분류만 기록한다.
    const type =
      error instanceof SyntaxError
        ? 'SyntaxError'
        : error instanceof TypeError
          ? 'TypeError'
          : 'UnknownError';
    console.error('Unexpected non-API error', type);
    return;
  }
  if (!('status' in error)) return;
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
  queryCache: new QueryCache({
    onError: (error, query) => {
      handleAuthError(error);
      // ['me'] 계열 조회의 실패로 자신을 다시 무효화하면 재조회가 끝없이 반복된다.
      if (isApiError(error) && query.queryKey[0] !== queryKeys.me[0]) {
        refreshMeIfTokenInvalid(error.error.reason);
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      handleAuthError(error);
      if (isApiError(error)) refreshMeIfTokenInvalid(error.error.reason);
    },
  }),
});
