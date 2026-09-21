import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { api, errorMessage } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';

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
  const [page, setPage] = useState(1);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { data: identity } = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.getMe({ signal }),
  });

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
  });

  const profile = profileQuery.data;
  const interviewList = interviewsQuery.data;
  const completedInterviews = (interviewList?.interviews ?? []).filter(
    (item) => item.status === 'completed',
  );
  const totalPages = interviewList ? Math.ceil(interviewList.total / interviewList.size) : 1;

  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      <Header active="mypage" />

      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
        <h1 className="text-lg font-bold">
          {`${identity?.name ?? profile?.name ?? ''} 님의 정보`}
        </h1>

        <section className="mt-5 flex flex-col gap-4 rounded-lg border border-accent/10 bg-surface p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">내 정보</h2>
            <button type="button" className="text-xs text-muted hover:underline">
              정보 수정
            </button>
          </div>

          {profileQuery.isLoading && <p className="text-sm text-muted">불러오는 중...</p>}
          {profileQuery.isError && <p className="text-sm text-error">정보를 불러오지 못했어요.</p>}

          {profile && (
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <img
                src={profile.avatarUrl}
                alt={profile.name}
                className="h-16 w-16 shrink-0 rounded-full object-cover"
              />
              <div className="flex min-w-0 w-full flex-1 flex-col gap-2 text-xs sm:flex-row sm:gap-8">
                <div className="flex min-w-0 flex-1 flex-col gap-2 sm:pl-8">
                  <div className="flex gap-2">
                    <dt className="w-[60px] shrink-0 text-muted">이름</dt>
                    <dd className="min-w-0 break-words font-semibold text-ink">{profile.name}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-[60px] shrink-0 text-muted">희망 직무</dt>
                    <dd className="min-w-0 break-words font-semibold text-ink">
                      {profile.desiredPosition ?? '-'}
                    </dd>
                  </div>
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex gap-2">
                    <dt className="w-[60px] shrink-0 text-muted">아이디</dt>
                    <dd className="min-w-0 break-words font-semibold text-ink">
                      {profile.loginId ?? '-'}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-[60px] shrink-0 text-muted">GitHub</dt>
                    <dd className="flex min-w-0 flex-wrap items-center gap-2 break-words font-semibold text-ink">
                      {profile.github.linked ? (
                        <>
                          <span>@{profile.github.login}</span>
                          <span className="whitespace-nowrap rounded-full bg-accent-soft px-2 py-0.5 text-xs font-normal text-accent">
                            연동됨 · 레포 {profile.github.publicRepoCount}개
                          </span>
                        </>
                      ) : (
                        <span className="font-normal text-muted">연동 안 됨</span>
                      )}
                    </dd>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="mt-4 rounded-lg border border-accent/10 bg-surface px-5 pb-2 pt-5">
          <h2 className="text-sm font-bold text-ink">
            면접 이력{profile ? ` · 총 ${profile.interviewSummary.totalCount}회` : ''}
          </h2>

          {interviewsQuery.isLoading && <p className="mt-6 text-sm text-muted">불러오는 중...</p>}
          {interviewsQuery.isError && (
            <p className="mt-6 text-sm text-error">이력을 불러오지 못했어요.</p>
          )}

          {interviewList && completedInterviews.length === 0 && (
            <p className="mt-6 text-sm text-muted">아직 완료된 면접이 없어요.</p>
          )}

          {completedInterviews.length > 0 && (
            <ul className="mt-6 divide-y divide-line-soft text-xs text-ink">
              {completedInterviews.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-col items-start justify-between gap-3 py-3 sm:flex-row sm:items-center sm:gap-4 sm:py-2"
                >
                  <div className="min-w-0 break-words">
                    <p className="font-bold">
                      {item.companyName} · {item.position}
                    </p>
                    <p className="mt-1 text-[10.5px] text-muted">
                      {formatDate(item.completedAt)} · {item.techStack.join('/')} ·{' '}
                      {item.careerLevel}
                    </p>
                  </div>
                  <div className="flex flex-1 flex-wrap gap-2">
                    {item.repositoryNames.map((name) => (
                      <span
                        key={name}
                        className="max-w-full break-words rounded-full bg-accent-soft px-2 py-1 text-[10.5px] text-ink"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-bold">
                      {item.totalScore}
                      <span className="font-normal text-muted">/100</span>
                    </span>
                    <button
                      type="button"
                      className="text-accent hover:underline"
                      onClick={() => navigate(`/interview/${item.id}/report`)}
                    >
                      리포트 보기 →
                    </button>
                  </div>
                </li>
              ))}
            </ul>
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

        <div className="mt-4 flex items-center justify-between text-xs">
          <p className="text-muted">계정을 삭제하려면 고객센터로 문의해주세요.</p>
          <button
            type="button"
            className="rounded-lg border border-line px-4 py-2.5 font-bold hover:bg-surface"
            onClick={() => dialogRef.current?.showModal()}
          >
            로그아웃
          </button>
        </div>
      </main>

      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>

      <dialog ref={dialogRef} className="logout-dialog" aria-labelledby="logout-title">
        <h2 id="logout-title" className="text-base font-bold">
          로그아웃 하시겠어요?
        </h2>
        <p className="mt-2 text-sm text-muted">다시 로그인하려면 GitHub 인증이 필요해요.</p>
        {logoutMutation.error && (
          <p className="error-banner mt-4" role="alert">
            {errorMessage(logoutMutation.error)}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-line px-4 py-2 text-sm font-medium"
            disabled={logoutMutation.isPending}
            onClick={() => dialogRef.current?.close()}
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
      </dialog>
    </div>
  );
}
