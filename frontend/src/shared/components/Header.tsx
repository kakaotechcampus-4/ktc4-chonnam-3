import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';

type ActivePage = 'home' | 'mypage' | 'interview';

type HeaderProps = {
  active: ActivePage;
  githubLinked?: boolean;
  name?: string;
  avatarUrl?: string | null;
};

export default function Header({ active, githubLinked, name, avatarUrl }: HeaderProps) {
  const { data: identity } = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ signal }),
  });
  // 상세 API가 아직 제공되지 않거나 실패해도 인증된 사용자 정보는 유지한다.
  githubLinked = identity?.githubLinked ?? githubLinked;
  name = identity?.name ?? name;
  avatarUrl = identity ? identity.avatarUrl : avatarUrl;

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft bg-surface px-4 py-3 sm:px-6">
      <div className="flex min-w-0 items-center gap-3 sm:gap-8">
        <span className="shrink-0 text-lg font-bold">DEVON</span>
        <nav className="flex items-center gap-1 text-sm" aria-label="주요 메뉴">
          {active === 'home' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">홈</span>
          ) : (
            <Link to="/home" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              홈
            </Link>
          )}
          {active === 'interview' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              모의면접
            </span>
          ) : (
            <Link to="/interview/new" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              모의면접
            </Link>
          )}
          {active === 'mypage' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              마이페이지
            </span>
          ) : (
            <Link to="/mypage" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              마이페이지
            </Link>
          )}
        </nav>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {githubLinked && (
          <span className="hidden rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent sm:inline">
            GitHub 연동됨
          </span>
        )}
        <span className="hidden max-w-32 truncate text-sm sm:inline">{name}</span>
        <Link to="/mypage" aria-label="내 계정">
          {avatarUrl ? (
            <img src={avatarUrl} alt={name ?? ''} className="h-8 w-8 rounded-full object-cover" />
          ) : (
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
              {name?.charAt(0) ?? ''}
            </span>
          )}
        </Link>
      </div>
    </header>
  );
}
