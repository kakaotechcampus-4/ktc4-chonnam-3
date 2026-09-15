import { useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { api, errorMessage } from '@/shared/api';
import AppHeader from '@/shared/components/AppHeader';
import { queryKeys } from '@/shared/queryKeys';

export default function MyPage() {
  const { data } = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ signal }),
  });
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string>();

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError(undefined);
    try {
      await api.logout();
    } catch (error) {
      setLogoutError(errorMessage(error));
      setIsLoggingOut(false);
    }
  }

  return (
    <div className="min-h-svh bg-paper">
      <AppHeader />
      <main className="page-shell max-w-3xl">
        <p className="section-label">계정</p>
        <h1 className="page-title">마이페이지</h1>
        <section className="identity-panel mt-8">
          {data?.avatarUrl ? (
            <img className="identity-avatar" src={data.avatarUrl} alt="" />
          ) : (
            <span className="identity-avatar grid place-items-center" aria-hidden="true">
              {data?.name?.[0] ?? '?'}
            </span>
          )}
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold">{data?.name}</h2>
            <p className="mt-1 text-sm text-muted">
              {data?.githubLinked
                ? 'GitHub 계정이 연결되어 있습니다.'
                : 'GitHub 연결을 확인해주세요.'}
            </p>
          </div>
        </section>
        <div className="mt-10 border-t border-line-soft pt-6">
          <button
            className="button-danger"
            type="button"
            onClick={() => dialogRef.current?.showModal()}
          >
            로그아웃
          </button>
        </div>
      </main>

      <dialog ref={dialogRef} className="logout-dialog" aria-labelledby="logout-title">
        <h2 id="logout-title" className="text-lg font-bold">
          로그아웃할까요?
        </h2>
        <p className="mt-2 text-sm text-muted">다시 이용하려면 GitHub 로그인이 필요합니다.</p>
        {logoutError && (
          <p className="error-banner mt-4" role="alert">
            {logoutError}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button
            className="button-secondary"
            type="button"
            disabled={isLoggingOut}
            onClick={() => dialogRef.current?.close()}
          >
            취소
          </button>
          <button
            className="button-danger-solid"
            type="button"
            disabled={isLoggingOut}
            onClick={handleLogout}
          >
            {isLoggingOut ? '로그아웃 중' : '로그아웃'}
          </button>
        </div>
      </dialog>
    </div>
  );
}
