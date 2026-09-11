import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import type { ApiError } from '@/types/api';

export default function Home() {
  const navigate = useNavigate();

  const homeQuery = useQuery({
    queryKey: queryKeys.home,
    queryFn: api.getHome,
    refetchInterval: (query) =>
      query.state.data?.analysisStatus === 'syncing' ? 3000 : false,
  });

  const home = homeQuery.data;
  const errorReason = (homeQuery.error as ApiError | undefined)?.error?.reason;
  const githubTokenInvalid = errorReason === 'github_token_invalid';

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between border-b border-line-soft bg-surface px-6 py-3">
        <div className="flex items-center gap-8">
          <span className="text-lg font-bold">DEVON</span>
          <nav className="flex items-center gap-1 text-sm">
            <span className="rounded-full bg-accent-soft px-3 py-1.5 font-medium text-accent">
              홈
            </span>
            <a href="/interview/new" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              모의면접
            </a>
            <a href="/mypage" className="rounded-full px-3 py-1.5 text-muted hover:bg-paper">
              마이페이지
            </a>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {home?.githubLinked && (
            <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
              GitHub 연동됨
            </span>
          )}
          <span className="h-8 w-8 rounded-full bg-accent-soft" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-2xl font-bold">
          {homeQuery.isLoading ? '불러오는 중...' : `안녕하세요, ${home?.name ?? ''} 님!`}
        </h1>

        {githubTokenInvalid && (
          <div className="mt-4 flex items-center justify-between rounded-card border border-error-soft bg-error-soft px-4 py-3 text-sm">
            <span className="text-error">GitHub 연동이 만료됐어요. 다시 연동해주세요.</span>
            <a href="/auth/github/link" className="font-medium text-error hover:underline">
              GitHub 재연동
            </a>
          </div>
        )}
        {homeQuery.isError && !githubTokenInvalid && (
          <p className="mt-4 text-sm text-error">정보를 불러오지 못했어요.</p>
        )}

        {home && (
          <section className="mt-6 rounded-card border border-line-soft bg-surface p-6">
            {home.analysisStatus === 'syncing' && (
              <div className="flex items-center gap-3 py-6 text-sm text-muted">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
                GitHub 레포를 수집하고 있어요. 잠시만 기다려주세요.
              </div>
            )}

            {home.analysisStatus === 'no_repository' && (
              <p className="py-6 text-sm text-muted">
                공개 레포가 없어요. GitHub에 공개 레포를 추가하면 분석이 시작돼요.
              </p>
            )}

            {home.analysisStatus === 'no_interview' && (
              <div className="py-6 text-center">
                <p className="text-sm text-muted">아직 면접 기록이 없어요.</p>
                <button
                  type="button"
                  onClick={() => navigate('/interview/new')}
                  className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white"
                >
                  첫 면접 시작하기
                </button>
              </div>
            )}

            {home.analysisStatus === 'completed' && home.analysis && (
              <div>
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">
                    GitHub 분석 · 레포 {home.analysis.basedOnRepoCount}개 기반
                  </h2>
                  <a href="#" className="text-xs text-muted hover:underline">
                    연동 관리
                  </a>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-8">
                  <div>
                    <p className="text-xs font-medium text-muted">주로 사용하는 언어</p>
                    <div className="mt-3 space-y-2.5">
                      {home.analysis.languages.map((lang) => (
                        <div key={lang.name} className="flex items-center gap-3 text-sm">
                          <span className="w-16 shrink-0">{lang.name}</span>
                          <div className="h-1.5 flex-1 rounded-full bg-line-soft">
                            <div
                              className="h-1.5 rounded-full bg-accent"
                              style={{ width: `${lang.ratio}%` }}
                            />
                          </div>
                          <span className="w-8 shrink-0 text-right text-muted">
                            {lang.ratio}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-medium text-muted">주요 프로젝트 유형</p>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      {home.analysis.projectTypes.map((type) => (
                        <span
                          key={type}
                          className="rounded-md bg-paper px-3 py-2 text-center text-xs text-ink"
                        >
                          {type}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <p className="mt-5 border-t border-line-soft pt-4 text-sm text-muted">
                  {home.analysis.roleSummary}
                </p>
              </div>
            )}
          </section>
        )}

        <button
          type="button"
          onClick={() => navigate('/interview/new')}
          className="mt-6 flex w-full items-center gap-4 rounded-card border border-line-soft bg-surface px-6 py-5 text-left hover:bg-accent-soft"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-white">
            ✦
          </span>
          <span className="flex-1">
            <p className="font-semibold">AI 모의면접</p>
            <p className="mt-1 text-sm text-muted">프로젝트 기반 실전 면접</p>
          </span>
          <span className="text-accent">→</span>
        </button>
      </main>
    </div>
  );
}
