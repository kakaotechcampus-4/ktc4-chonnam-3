import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { isApiError } from '@/types/api';

const MAX_REPOSITORIES = 5;

export default function RepoSelect() {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const resultQuery = useQuery({
    queryKey: queryKeys.analysisResult(runId),
    queryFn: () => api.getAnalysisRunResult(runId),
    enabled: !!runId,
  });

  const [selectedIds, setSelectedIds] = useState<string[] | null>(null);

  const result = resultQuery.data;
  const defaultSelected = result?.repositories.filter((r) => r.recommended).map((r) => r.id) ?? [];
  const selected = selectedIds ?? defaultSelected;

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const current = prev ?? defaultSelected;
      if (current.includes(id)) return current.filter((x) => x !== id);
      if (current.length >= MAX_REPOSITORIES) return current;
      return [...current, id];
    });
  }

  const createInterviewMutation = useMutation({
    mutationFn: () => api.createInterview({ runId, repositoryIds: selected }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['interviews'] });
      navigate(`/interview/${data.interviewId}/prepare`);
    },
  });

  const mutationError = createInterviewMutation.error;
  const errorReason = isApiError(mutationError) ? mutationError.error.reason : null;
  const tooMany = errorReason === 'too_many_repositories';
  const submitError = tooMany
    ? '레포는 최대 5개까지 선택할 수 있어요.'
    : createInterviewMutation.isError
      ? '면접을 시작하지 못했어요. 잠시 후 다시 시도해주세요.'
      : null;

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header active="interview" />

      <main className="flex flex-1 flex-col items-center px-10 pb-12 pt-10">
        <div className="w-full max-w-4xl">
          <p className="text-[11px] font-bold tracking-wide text-muted">모의면접 · 2 / 3</p>
          <h1 className="mt-3 text-xl font-bold">면접에 사용할 GitHub 레포를 선택해주세요</h1>
          <p className="mt-2 text-sm text-muted">
            AI가 JD와 관련성이 높은 레포를 자동으로 선택했어요. 직접 추가하거나 제외할 수 있어요.
          </p>

          {resultQuery.isLoading && <p className="mt-8 text-sm text-muted">불러오는 중...</p>}
          {resultQuery.isError && (
            <p className="mt-8 text-sm text-error">레포 목록을 불러오지 못했어요.</p>
          )}

          {result && (
            <>
              <div className="mt-5 flex gap-4">
                <div className="flex-1 rounded-[10px] border border-line-soft p-4">
                  <p className="text-[11.5px] font-bold tracking-wide text-muted">내 GitHub 레포</p>
                  <ul className="mt-3 flex flex-col gap-2">
                    {result.repositories.map((repo) => {
                      const checked = selected.includes(repo.id);
                      return (
                        <li key={repo.id}>
                          <button
                            type="button"
                            onClick={() => toggle(repo.id)}
                            className={
                              checked
                                ? 'flex w-full gap-2.5 rounded-lg border border-accent bg-accent-soft px-3 py-2.5 text-left'
                                : 'flex w-full gap-2.5 rounded-lg border border-line-soft px-3 py-2.5 text-left'
                            }
                          >
                            <span
                              className={
                                checked
                                  ? 'mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border-[1.5px] border-accent bg-accent text-[11px] font-bold text-white'
                                  : 'mt-0.5 h-[18px] w-[18px] shrink-0 rounded-[5px] border-[1.5px] border-line'
                              }
                            >
                              {checked && '✓'}
                            </span>
                            <span className="flex-1">
                              <span className="flex items-center gap-2">
                                <span className="text-[13px] font-bold text-ink">{repo.name}</span>
                                {repo.recommended && (
                                  <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-bold text-accent">
                                    AI 추천
                                  </span>
                                )}
                              </span>
                              {repo.languages.length > 0 && (
                                <span className="mt-1 flex flex-wrap gap-1.5">
                                  {repo.languages.map((lang) => (
                                    <span
                                      key={lang}
                                      className="rounded-full bg-paper px-2 py-0.5 text-[11px] text-muted"
                                    >
                                      {lang}
                                    </span>
                                  ))}
                                </span>
                              )}
                              <span className="mt-1 block text-[11.5px] text-muted">
                                {repo.recommendReason}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="mt-3 flex items-center justify-between">
                    <p className="text-[11.5px] text-muted">{selected.length}개 레포 선택됨</p>
                    <button
                      type="button"
                      className="rounded-md border border-dashed border-line px-2.5 py-1.5 text-[11.5px] text-muted"
                    >
                      + Private 레포 직접 추가
                    </button>
                  </div>
                </div>

                <div className="w-[260px] shrink-0 rounded-[10px] border border-line-soft p-3.5">
                  <p className="text-[11.5px] font-bold tracking-wide text-muted">JD 요구사항</p>
                  <ul className="mt-3 flex flex-col gap-2">
                    {result.jdRequirements.map((req, i) => (
                      <li key={i} className="text-xs text-ink">
                        {req}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {submitError && <p className="mt-3 text-sm text-error">{submitError}</p>}

              <button
                type="button"
                disabled={selected.length === 0 || createInterviewMutation.isPending}
                onClick={() => createInterviewMutation.mutate()}
                className="mt-5 w-full rounded-lg bg-accent py-3 text-sm font-bold text-white disabled:opacity-50"
              >
                {createInterviewMutation.isPending ? '면접 준비 중...' : '선택한 레포로 면접 시작'}
              </button>
            </>
          )}
        </div>
      </main>

      <footer className="flex items-center border-t border-line-soft px-8 py-3.5 text-[11.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}
