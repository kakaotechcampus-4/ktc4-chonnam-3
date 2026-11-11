import { useQuery } from '@tanstack/react-query';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { api } from '@/shared/api';
import { isSessionEnding } from '@/shared/queryClient';
import { queryKeys } from '@/shared/queryKeys';

export default function RequireAuth() {
  const me = useQuery({ queryKey: queryKeys.me, queryFn: api.getMe });
  // 하위 경로만 바뀌면(/mypage → /home) 이 레이아웃은 다시 렌더되지 않아 아래 종료 확인을 건너뛴다.
  // 로그아웃 직후 /login이 그려지기 전에 뒤로 가기가 오면 보호 화면이 죽은 재시도 화면으로 남는다.
  // 위치를 구독해 이동마다 다시 확인한다.
  useLocation();

  // 캐시를 비우는 동안 하위 보호 화면이 다시 데이터를 조회하지 않도록 막는다.
  if (isSessionEnding()) return <Navigate to="/login" replace />;

  if (me.isPending) {
    return (
      <p role="status" className="p-8 text-muted">
        로그인 상태를 확인하고 있어요.
      </p>
    );
  }
  // 인증 오류의 이동은 전역에서 처리하며, 네트워크·서버 장애는 로그인 만료로 취급하지 않는다.
  // 이미 확인한 세션의 백그라운드 재조회 실패로는 보던 화면을 가리지 않는다.
  if (me.isError && !me.data) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-paper">
        <p role="alert" className="text-error">
          로그인 상태를 확인하지 못했어요.
        </p>
        <button
          type="button"
          onClick={() => void me.refetch()}
          className="rounded-md border border-line px-4 py-2"
        >
          다시 시도
        </button>
      </main>
    );
  }
  return <Outlet />;
}
