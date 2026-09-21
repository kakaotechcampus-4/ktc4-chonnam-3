import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { STEP_GROUPS, groupStatus } from '@/features/analysis/steps';
import type { RunStatus, StepKey, StepStatus } from '@/types/api';

type StepMap = Record<StepKey, StepStatus>;

const INITIAL_STEPS: StepMap = {
  doc_extract: 'pending',
  repo_select: 'pending',
  repo_detail: 'pending',
  jd_fetch: 'pending',
  jd_extract: 'pending',
  repo_analyze: 'pending',
  match_score: 'pending',
};

export default function Analyzing() {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [sseSteps, setSseSteps] = useState<Partial<StepMap>>({});
  const [sseStatus, setSseStatus] = useState<RunStatus | null>(null);
  const sseOpenedRef = useRef(false);

  // REST 스냅샷을 기다렸다가 SSE를 열면, "스냅샷을 읽은 시점"과 "SSE가 실제로
  // 연결된 시점" 사이에 일어난 전환을 영영 놓칠 수 있다. runId를 알자마자(REST
  // 응답을 기다리지 않고) 바로 구독해서 그 틈 자체를 없앤다.
  const runQuery = useQuery({
    queryKey: queryKeys.analysisRun(runId),
    queryFn: () => api.getAnalysisRun(runId),
    enabled: !!runId,
    // SSE 연결 핸드셰이크 구간처럼 순서를 바꿔도 못 막는 틈을 위한 안전장치로,
    // SSE가 정상 동작 중이어도 계속 폴링해서 놓친 이벤트가 있으면 몇 초 안에 따라잡는다.
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });

  useEffect(() => {
    if (!runId || sseOpenedRef.current) return;
    sseOpenedRef.current = true;

    const source = new EventSource(api.analysisRunEventsUrl(runId), { withCredentials: true });

    source.onmessage = (event) => {
      const data = JSON.parse(event.data) as
        | { type: 'step'; key: StepKey; status: StepStatus }
        | { type: 'completed' }
        | { type: 'failed'; reason: string };

      if (data.type === 'step') {
        setSseSteps((prev) => ({ ...prev, [data.key]: data.status }));
      } else if (data.type === 'completed') {
        setSseStatus('completed');
        source.close();
      } else if (data.type === 'failed') {
        setSseStatus('failed');
        source.close();
      }
    };

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [runId]);

  const steps: StepMap = {
    ...INITIAL_STEPS,
    ...Object.fromEntries((runQuery.data?.steps ?? []).map((s) => [s.key, s.status])),
    ...sseSteps,
  };
  const runStatus: RunStatus = sseStatus ?? runQuery.data?.status ?? 'running';
  const hasFailedStep = Object.values(steps).some((status) => status === 'failed');

  useEffect(() => {
    if (!runId) return;
    if (runStatus === 'completed') navigate(`/interview/repos/${runId}`);
    if (runStatus === 'failed') navigate(`/interview/failed/${runId}`);
  }, [runStatus, runId, navigate]);

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header active="interview" />

      <main className="flex flex-1 flex-col items-center px-7 pb-7 pt-6">
        <div className="flex w-[380px] max-w-full flex-col gap-4 py-14">
          <p className="text-[11px] font-bold text-accent">모의면접 · 분석 중</p>

          <div className="flex items-center gap-3">
            {hasFailedStep ? (
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-error-soft text-sm font-bold text-error">
                !
              </span>
            ) : (
              <span className="h-7 w-7 shrink-0 animate-spin rounded-full border-[3px] border-accent-soft border-t-accent" />
            )}
            <h1 className="flex-1 text-base font-bold">GitHub 레포를 분석하고 있어요</h1>
          </div>

          <ul className="flex flex-col gap-3">
            {STEP_GROUPS.map((group) => {
              const status = groupStatus(group.keys, steps);
              return (
                <li key={group.label} className="flex items-center gap-2.5">
                  {status === 'completed' && (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent">
                      ✓
                    </span>
                  )}
                  {status === 'running' && (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent">
                      ···
                    </span>
                  )}
                  {status === 'failed' && (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-error-soft text-[10px] font-bold text-error">
                      !
                    </span>
                  )}
                  {status === 'pending' && (
                    <span className="h-5 w-5 shrink-0 rounded-full bg-line-soft" />
                  )}
                  <span
                    className={
                      status === 'running'
                        ? 'flex-1 text-[13px] font-bold'
                        : status === 'failed'
                          ? 'flex-1 text-[13px] font-bold text-error'
                          : status === 'pending'
                            ? 'flex-1 text-[13px] text-muted'
                            : 'flex-1 text-[13px]'
                    }
                  >
                    {group.label}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </main>

      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}
