import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';

export default function AppHeader() {
  const location = useLocation();
  const { data } = useQuery({ queryKey: queryKeys.me, queryFn: api.getMe });

  const isInterviewTab = location.pathname.startsWith('/interview');

  return (
    <header className="flex items-center justify-between border-b border-line-soft px-8 py-4">
      <div className="flex items-center gap-8">
        <span className="text-lg font-bold text-ink">DEVON</span>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            to="/home"
            className={`rounded-full px-4 py-2 ${
              !isInterviewTab ? 'bg-accent-soft text-accent' : 'text-muted'
            }`}
          >
            홈
          </Link>
          <Link
            to="/interview/new"
            className={`rounded-full px-4 py-2 ${
              isInterviewTab ? 'bg-accent-soft text-accent' : 'text-muted'
            }`}
          >
            모의면접
          </Link>
        </nav>
      </div>
      <div className="flex items-center gap-3">
        {data?.githubLinked && (
          <span className="rounded-full border border-line px-3 py-1 text-sm text-muted">
            ✓ GitHub 연동됨
          </span>
        )}
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-soft text-sm font-medium text-accent">
          {data?.name?.[0] ?? '?'}
        </span>
      </div>
    </header>
  );
}
