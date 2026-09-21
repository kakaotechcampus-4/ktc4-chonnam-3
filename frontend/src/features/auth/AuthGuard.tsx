import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { api, errorMessage, isAuthFailure } from '@/shared/api';
import { subscribeAuthChanges } from '@/shared/authEvents';
import { queryKeys } from '@/shared/queryKeys';

export default function AuthGuard({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const isLogin = location.pathname === '/login';
  const [authRedirect, setAuthRedirect] = useState<string>();

  useEffect(
    () =>
      subscribeAuthChanges(({ reason, redirect }) => {
        if (redirect) {
          const blocked = reason === 'account_suspended' || reason === 'account_withdrawn';
          // 캐시를 지우기 전에 조회를 중지하고, 새 문서를 열지 않아 같은 실패를 다시 갱신하지 않는다.
          setAuthRedirect(`/login${blocked ? `?error=${reason}` : ''}`);
        }
        void queryClient.cancelQueries().then(() => {
          if (redirect) queryClient.clear();
        });
      }),
    [queryClient],
  );

  const identity = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ anonymous: isLogin, signal }),
    retry: false,
    enabled: !authRedirect,
  });

  if (authRedirect) {
    return location.pathname + location.search === authRedirect ? (
      children
    ) : (
      <Navigate to={authRedirect} replace />
    );
  }

  if (isLogin) return identity.data ? <Navigate to="/home" replace /> : children;

  if (identity.isPending) {
    return (
      <main className="grid min-h-svh place-items-center px-6" aria-busy="true">
        <p className="text-sm text-muted">계정을 확인하고 있습니다.</p>
      </main>
    );
  }

  if (identity.error) {
    // 인증 거부가 확인된 경우에만 로그인을 요구하고, 장애 시에는 재시도를 위해 사용자 캐시를 유지한다.
    if (isAuthFailure(identity.error)) return <Navigate to="/login" replace />;
    return (
      <main className="grid min-h-svh place-items-center px-6">
        <section className="w-full max-w-sm rounded-card bg-surface p-6 text-center" role="alert">
          <h1 className="text-xl font-bold">연결을 확인해주세요</h1>
          <p className="mt-2 text-sm text-muted">{errorMessage(identity.error)}</p>
          <button
            className="mt-6 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white"
            type="button"
            onClick={() => identity.refetch()}
          >
            다시 시도
          </button>
        </section>
      </main>
    );
  }

  return children;
}
