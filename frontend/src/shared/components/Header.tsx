type ActivePage = 'home' | 'mypage';

type HeaderProps = {
  active: ActivePage;
  githubLinked?: boolean;
  avatarUrl?: string;
  avatarAlt?: string;
};

export default function Header({ active, githubLinked, avatarUrl, avatarAlt }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-line-soft bg-surface px-6 py-3">
      <div className="flex items-center gap-8">
        <span className="text-lg font-bold">DEVON</span>
        <nav className="flex items-center gap-1 text-sm">
          {active === 'home' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">홈</span>
          ) : (
            <a href="/home" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              홈
            </a>
          )}
          <a href="/interview/new" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
            모의면접
          </a>
          {active === 'mypage' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              마이페이지
            </span>
          ) : (
            <a href="/mypage" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              마이페이지
            </a>
          )}
        </nav>
      </div>
      <div className="flex items-center gap-3">
        {githubLinked && (
          <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
            GitHub 연동됨
          </span>
        )}
        {avatarUrl ? (
          <img src={avatarUrl} alt={avatarAlt ?? ''} className="h-8 w-8 rounded-full object-cover" />
        ) : (
          <span className="h-8 w-8 rounded-full bg-line-soft" />
        )}
      </div>
    </header>
  );
}
