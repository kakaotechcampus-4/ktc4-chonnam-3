import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';

export default function AppHeader() {
  const location = useLocation();
  const { data } = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ signal }),
  });
  const isInterviewTab = location.pathname.startsWith('/interview');

  return (
    <header className="app-header">
      <div className="flex min-w-0 items-center gap-4 sm:gap-8">
        <Link className="shrink-0 text-lg font-bold text-ink" to="/home">
          DEVON
        </Link>
        <nav className="flex items-center gap-1 text-sm" aria-label="주요 메뉴">
          <Link className={!isInterviewTab ? 'nav-link nav-link-active' : 'nav-link'} to="/home">
            홈
          </Link>
          <Link
            className={isInterviewTab ? 'nav-link nav-link-active' : 'nav-link'}
            to="/interview/new"
          >
            모의면접
          </Link>
        </nav>
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        {data?.githubLinked && <span className="github-badge">GitHub 연결됨</span>}
        <span className="header-name">{data?.name}</span>
        <Link className="avatar-link" to="/mypage" aria-label="마이페이지">
          {data?.avatarUrl ? (
            <img src={data.avatarUrl} alt="" />
          ) : (
            <span aria-hidden="true">{data?.name?.[0] ?? '?'}</span>
          )}
        </Link>
      </div>
    </header>
  );
}
