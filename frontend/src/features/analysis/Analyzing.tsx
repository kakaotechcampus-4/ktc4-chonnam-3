import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import type { RunStatus, StepKey, StepStatus } from '@/types/api';

// Figma(3-2 · GitHub 분석 중)의 체크리스트 순서 그대로 — StepKey와의 정확한 1:1 대응은
// 미확인, 개수(4개)와 위치로만 맞춤. CLAUDE.md의 4-3-v2 체크리스트도 같은 미확인 상태
const STEP_ORDER: StepKey[] = ['fetch_repos', 'extract_jd', 'match_score', 'prepare_result'];

const STEP_LABELS: Record<StepKey, string> = {
  fetch_repos: 'Repository 구조 확인',
  extract_jd: 'README · 설정 파일 읽기',
  match_score: '주요 기술 스택 감지 중',
  prepare_result: 'JD 요구사항과 매칭',
};

type StepMap = Record<StepKey, StepStatus>;

const INITIAL_STEPS: StepMap = {
  fetch_repos: 'pending',
  extract_jd: 'pending',
  match_score: 'pending',
  prepare_result: 'pending',
};

export default function Analyzing() {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [steps, setSteps] = useState<StepMap>(INITIAL_STEPS);
  const [runStatus, setRunStatus] = useState<RunStatus>('running');
  const [ssePending, setSsePending] = useState(true);

  const pollQuery = useQuery({
    queryKey: queryKeys.analysisRun(runId),
    queryFn: () => api.getAnalysisRun(runId),
    enabled: !!runId && !ssePending,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });

  useEffect(() => {
    if (!runId) return;

    const source = new EventSource(api.analysisRunEventsUrl(runId), { withCredentials: true });

    source.onmessage = (event) => {
      const data = JSON.parse(event.data) as
        | { type: 'step'; key: StepKey; status: StepStatus }
        | { type: 'completed' }
        | { type: 'failed'; reason: string };

      if (data.type === 'step') {
        setSteps((prev) => ({ ...prev, [data.key]: data.status }));
      } else if (data.type === 'completed') {
        setRunStatus('completed');
        source.close();
      } else if (data.type === 'failed') {
        setRunStatus('failed');
        source.close();
      }
    };

    source.onerror = () => {
      source.close();
      setSsePending(false);
    };

    return () => source.close();
  }, [runId]);

  const effectiveStatus = ssePending ? runStatus : (pollQuery.data?.status ?? runStatus);
  const effectiveSteps = ssePending
    ? steps
    : pollQuery.data
      ? { ...steps, ...Object.fromEntries(pollQuery.data.steps.map((s) => [s.key, s.status])) }
      : steps;

  useEffect(() => {
    if (!runId) return;
    if (effectiveStatus === 'completed') navigate(`/interview/repos/${runId}`);
    if (effectiveStatus === 'failed') navigate(`/interview/failed/${runId}`);
  }, [effectiveStatus, runId, navigate]);

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header active="interview" />

      <main className="flex flex-1 flex-col items-center px-7 pb-7 pt-6">
        <div className="flex w-[380px] max-w-full flex-col gap-4 py-14">
          <p className="text-[11px] font-bold text-accent">모의면접 · 분석 중</p>

          <div className="flex items-center gap-3">
            <span className="h-7 w-7 shrink-0 animate-spin rounded-full border-[3px] border-accent-soft border-t-accent" />
            <h1 className="flex-1 text-base font-bold">GitHub 레포를 분석하고 있어요</h1>
          </div>

          <ul className="flex flex-col gap-3">
            {STEP_ORDER.map((key) => {
              const status = effectiveSteps[key];
              return (
                <li key={key} className="flex items-center gap-2.5">
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
                  {status === 'pending' && (
                    <span className="h-5 w-5 shrink-0 rounded-full bg-line-soft" />
                  )}
                  <span
                    className={
                      status === 'running'
                        ? 'flex-1 text-[13px] font-bold'
                        : status === 'pending'
                          ? 'flex-1 text-[13px] text-muted'
                          : 'flex-1 text-[13px]'
                    }
                  >
                    {STEP_LABELS[key]}
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
