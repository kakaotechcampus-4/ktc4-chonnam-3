type ActivePage = 'home' | 'mypage' | 'interview';

type HeaderProps = {
  active: ActivePage;
  githubLinked?: boolean;
  name?: string;
  avatarUrl?: string;
  /**
   * GitHub 연동 배지를 대체하는 내용. 둘은 같은 자리를 쓰며 이 값이 있으면
   * githubLinked는 무시된다. 면접 진행 화면의 잔여 시간이 쓴다.
   */
  statusSlot?: React.ReactNode;
};

export default function Header({ active, githubLinked, name, avatarUrl, statusSlot }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-line-soft bg-surface px-6 py-3">
      <div className="flex items-center gap-8">
        <span className="text-lg font-bold">DEVON</span>
        <nav className="flex items-center gap-1 text-sm">
          {active === 'home' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              홈
            </span>
          ) : (
            <a href="/home" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              홈
            </a>
          )}
          {active === 'interview' ? (
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              모의면접
            </span>
          ) : (
            <a href="/interview/new" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              모의면접
            </a>
          )}
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
        {statusSlot}
        {!statusSlot && githubLinked && (
          <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
            GitHub 연동됨
          </span>
        )}
        <a href="/mypage" aria-label="마이페이지">
          {avatarUrl ? (
            <img src={avatarUrl} alt={name ?? ''} className="h-8 w-8 rounded-full object-cover" />
          ) : (
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
              {name?.charAt(0) ?? ''}
            </span>
          )}
        </a>
      </div>
    </header>
  );
}
