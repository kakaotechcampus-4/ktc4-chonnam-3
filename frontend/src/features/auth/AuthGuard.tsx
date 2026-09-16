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
    // Only confirmed auth rejection requires login; outages preserve cached identity for retry.
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
