import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { api, errorMessage, isAuthFailure } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';

export default function AuthGuard({ children }: { children: ReactNode }) {
  const location = useLocation();
  const isLogin = location.pathname === '/login';
  const identity = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ anonymous: isLogin, signal }),
    retry: false,
  });

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
        <section className="status-panel text-center" role="alert">
          <h1 className="text-xl font-bold">연결을 확인해주세요</h1>
          <p className="mt-2 text-sm text-muted">{errorMessage(identity.error)}</p>
          <button className="button-primary mt-6" type="button" onClick={() => identity.refetch()}>
            다시 시도
          </button>
        </section>
      </main>
    );
  }

  return children;
}
