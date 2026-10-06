import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import { refreshMeIfTokenInvalid } from '@/shared/queryClient';
import Header from '@/shared/components/Header';
import Footer from '@/shared/components/Footer';
import { STEP_GROUPS, groupStatus } from '@/features/analysis/steps';
import type { StepKey, StepStatus } from '@/types/api';

export default function AnalysisFailed() {
  const { runId = '' } = useParams<{ runId: string }>();

  const runQuery = useQuery({
    queryKey: queryKeys.analysisRun(runId),
    queryFn: () => api.getAnalysisRun(runId),
    enabled: !!runId,
  });

  const run = runQuery.data;
  // 실패 사유는 200 응답 안의 값이라 전역 오류 처리가 보지 못한다.
  useEffect(() => refreshMeIfTokenInvalid(run?.failureReason), [run?.failureReason]);
  const stepStatus: Partial<Record<StepKey, StepStatus>> = Object.fromEntries(
    (run?.steps ?? []).map((s) => [s.key, s.status]),
  );

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header />

      <main className="flex flex-1 flex-col items-center px-7 pb-7 pt-6">
        <div className="flex w-[380px] max-w-full flex-col gap-4 py-14">
          <p className="text-[11px] font-bold text-accent">모의면접 · 분석 중</p>

          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-error-soft text-sm font-bold text-error">
              !
            </span>
            <h1 className="flex-1 text-base font-bold">GitHub 레포를 분석하지 못했어요</h1>
          </div>

          {run && (
            <ul className="flex flex-col gap-3">
              {STEP_GROUPS.map((group) => {
                const status = groupStatus(group.keys, stepStatus);
                const isFailed = status === 'failed';
                const isDone = status === 'completed';
                return (
                  <li key={group.label} className="flex items-center gap-2.5">
                    {isFailed && (
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-error-soft text-[10px] font-bold text-error">
                        !
                      </span>
                    )}
                    {!isFailed && isDone && (
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent">
                        ✓
                      </span>
                    )}
                    {!isFailed && !isDone && (
                      <span className="h-5 w-5 shrink-0 rounded-full bg-line-soft" />
                    )}
                    <span
                      className={
                        isFailed
                          ? 'flex-1 text-[13px] font-bold text-error'
                          : isDone
                            ? 'flex-1 text-[13px]'
                            : 'flex-1 text-[13px] text-muted'
                      }
                    >
                      {group.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
