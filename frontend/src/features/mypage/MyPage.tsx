import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';

const PAGE_SIZE = 10;

function formatDate(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

export default function MyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [logoutOpen, setLogoutOpen] = useState(false);

  const profileQuery = useQuery({
    queryKey: queryKeys.profile,
    queryFn: api.getProfile,
  });

  const interviewsQuery = useQuery({
    queryKey: queryKeys.interviews(page),
    queryFn: () => api.getInterviews({ page, size: PAGE_SIZE }),
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      navigate('/login');
    },
  });

  const profile = profileQuery.data;
  const interviewList = interviewsQuery.data;
  const completedInterviews = (interviewList?.interviews ?? []).filter(
    (item) => item.status === 'completed',
  );
  const totalPages = interviewList ? Math.ceil(interviewList.total / interviewList.size) : 1;

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between border-b border-line-soft bg-surface px-6 py-3">
        <div className="flex items-center gap-8">
          <span className="text-lg font-bold">DEVON</span>
          <nav className="flex items-center gap-1 text-sm">
            <a href="/home" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              홈
            </a>
            <a href="/interview/new" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              모의면접
            </a>
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              마이페이지
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {profile?.github.linked && (
            <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
              GitHub 연동됨
            </span>
          )}
          {profile ? (
            <img
              src={profile.avatarUrl}
              alt={profile.name}
              className="h-8 w-8 rounded-full object-cover"
            />
          ) : (
            <span className="h-8 w-8 rounded-full bg-line-soft" />
          )}
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <p className="text-sm font-medium text-accent">마이페이지</p>
        <h1 className="mt-1 text-2xl font-bold">
          {profileQuery.isLoading ? '불러오는 중...' : `${profile?.name ?? ''} 님의 정보`}
        </h1>

        <section className="mt-6 rounded-card border border-line-soft bg-surface p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-muted">내 정보</h2>
            <button
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-paper"
            >
              정보 수정
            </button>
          </div>

          {profileQuery.isLoading && <p className="mt-6 text-sm text-muted">불러오는 중...</p>}
          {profileQuery.isError && (
            <p className="mt-6 text-sm text-error">정보를 불러오지 못했어요.</p>
          )}

          {profile && (
            <div className="mt-6 flex items-start gap-6">
              <img
                src={profile.avatarUrl}
                alt={profile.name}
                className="h-16 w-16 shrink-0 rounded-full object-cover"
              />
              <dl className="grid flex-1 grid-cols-2 gap-x-8 gap-y-4 text-sm">
                <div>
                  <dt className="text-muted">이름</dt>
                  <dd className="mt-1 font-semibold">{profile.name}</dd>
                </div>
                <div>
                  <dt className="text-muted">아이디</dt>
                  <dd className="mt-1 font-semibold">{profile.loginId ?? '-'}</dd>
                </div>
                <div>
                  <dt className="text-muted">가입일</dt>
                  <dd className="mt-1 font-semibold">{formatDate(profile.joinedAt)}</dd>
                </div>
                <div>
                  <dt className="text-muted">GitHub</dt>
                  <dd className="mt-1 flex items-center gap-2 font-semibold">
                    {profile.github.linked ? (
                      <>
                        <span>@{profile.github.login}</span>
                        <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
                          연동됨 · 레포 {profile.github.publicRepoCount}개
                        </span>
                      </>
                    ) : (
                      <span className="text-muted">연동 안 됨</span>
                    )}
                  </dd>
                </div>
              </dl>
            </div>
          )}
        </section>

        <section className="mt-6 rounded-card border border-line-soft bg-surface p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-muted">
              면접 이력 · 총 {profile?.interviewSummary.totalCount ?? 0}회
            </h2>
            <p className="text-sm text-muted">
              평균 점수{' '}
              <span className="font-bold text-ink">
                {profile?.interviewSummary.averageScore ?? '-'}
                {profile?.interviewSummary.averageScore != null && '점'}
              </span>
            </p>
          </div>

          {interviewsQuery.isLoading && <p className="mt-6 text-sm text-muted">불러오는 중...</p>}
          {interviewsQuery.isError && (
            <p className="mt-6 text-sm text-error">이력을 불러오지 못했어요.</p>
          )}

          {interviewList && completedInterviews.length === 0 && (
            <p className="mt-6 text-sm text-muted">아직 완료된 면접이 없어요.</p>
          )}

          {completedInterviews.length > 0 && (
            <table className="mt-6 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line-soft text-muted">
                  <th className="pb-2 font-medium">일시</th>
                  <th className="pb-2 font-medium">공고</th>
                  <th className="pb-2 font-medium">사용 레포</th>
                  <th className="pb-2 font-medium">점수</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {completedInterviews.map((item) => (
                  <tr key={item.id} className="border-b border-line-soft last:border-0">
                    <td className="py-3 align-top text-muted">{formatDate(item.completedAt)}</td>
                    <td className="py-3 align-top">
                      <p className="font-semibold">
                        {item.companyName} · {item.position}
                      </p>
                    </td>
                    <td className="py-3 align-top">
                      <div className="flex flex-wrap gap-1">
                        {item.repositoryNames.map((name) => (
                          <span
                            key={name}
                            className="rounded-md bg-paper px-2 py-0.5 font-mono text-xs text-muted"
                          >
                            {name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 align-top">
                      <span className="font-bold">{item.totalScore}</span>
                      <span className="text-muted">/100</span>
                    </td>
                    <td className="py-3 align-top text-right">
                      <button
                        type="button"
                        className="font-medium text-accent hover:underline"
                        onClick={() => navigate(`/interview/${item.id}/report`)}
                      >
                        리포트 보기 →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <button
                type="button"
                className="rounded-md border border-line px-3 py-1 disabled:opacity-40"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                이전
              </button>
              <span className="text-muted">
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className="rounded-md border border-line px-3 py-1 disabled:opacity-40"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </button>
            </div>
          )}
        </section>

        <div className="mt-6 flex items-center justify-between text-sm">
          <p className="text-muted">계정을 삭제하려면 고객센터로 문의해주세요.</p>
          <button
            type="button"
            className="rounded-md border border-line px-4 py-2 font-medium hover:bg-surface"
            onClick={() => setLogoutOpen(true)}
          >
            로그아웃
          </button>
        </div>
      </main>

      {logoutOpen && (
        <div className="fixed inset-0 flex items-center justify-center bg-ink/40 px-4">
          <div className="w-full max-w-sm rounded-card bg-surface p-6">
            <h2 className="text-base font-bold">로그아웃 하시겠어요?</h2>
            <p className="mt-2 text-sm text-muted">다시 로그인하려면 GitHub 인증이 필요해요.</p>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-line px-4 py-2 text-sm font-medium"
                onClick={() => setLogoutOpen(false)}
              >
                취소
              </button>
              <button
                type="button"
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                disabled={logoutMutation.isPending}
                onClick={() => logoutMutation.mutate()}
              >
                {logoutMutation.isPending ? '로그아웃 중...' : '로그아웃'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
