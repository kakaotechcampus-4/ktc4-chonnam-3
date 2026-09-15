import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '@/shared/api';
import AppHeader from '@/shared/components/AppHeader';
import { queryKeys } from '@/shared/queryKeys';

export default function Home() {
  const { data } = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ signal }),
  });

  return (
    <div className="min-h-svh bg-paper">
      <AppHeader />
      <main className="page-shell">
        <p className="section-label">오늘의 준비</p>
        <h1 className="page-title">{data?.name}님, 반가워요</h1>
        <p className="page-copy">
          {data?.githubLinked
            ? 'GitHub 계정 연결이 완료되었습니다.'
            : 'GitHub 연결을 확인해주세요.'}
        </p>
        <div className="mt-8">
          <Link className="button-secondary" to="/mypage">
            내 정보 보기
          </Link>
        </div>
      </main>
    </div>
  );
}
