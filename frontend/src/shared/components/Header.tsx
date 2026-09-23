import { Link } from 'react-router-dom';

type ActivePage = 'home' | 'mypage' | 'interview';

type HeaderProps = {
  active: ActivePage;
  githubLinked?: boolean;
  name?: string;
  avatarUrl?: string;
};

export default function Header({ active, githubLinked, name, avatarUrl }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-line-soft bg-surface px-6 py-3">
      <div className="flex items-center gap-8">
        <span className="text-lg font-bold">DEVON</span>
        <nav className="flex items-center gap-1 text-sm">
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
      <div className="flex items-center gap-3">
        {githubLinked && (
          <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
            GitHub 연동됨
          </span>
        )}
        <Link to="/mypage" aria-label="마이페이지">
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
