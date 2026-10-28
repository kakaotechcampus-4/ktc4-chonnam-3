import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { api, BASE } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import { refreshMeIfTokenInvalid } from '@/shared/queryClient';
import Header from '@/shared/components/Header';
import Footer from '@/shared/components/Footer';
import RunLoadError from '@/features/analysis/RunLoadError';
import {
  STEP_GROUPS,
  groupStatus,
  postingUrlFrom,
  type AnalysisInputState,
} from '@/features/analysis/steps';
import type { StepKey, StepStatus } from '@/types/api';

type FailureAction = 'relink' | 'input' | 'none';

/**
 * failureReason 값은 frontend/docs/api-spec.md의 failureReason 표를 따른다. 없는 값은 DEFAULT_FAILURE.
 * GitHub 토큰 무효는 HTTP reason과 같은 github_token_invalid다(api-spec.md 변경 이력 2026-09-10).
 * input은 공고 입력 화면에 이전 URL을 채워 보낸다. 다시 분석은 사용자가 그 화면에서 시작한다.
 */
const FAILURE: Record<string, { message: string; action: FailureAction; label?: string }> = {
  github_token_invalid: {
    message: 'GitHub 연동이 만료됐어요. 다시 연동한 뒤 분석해주세요.',
    action: 'relink',
  },
  no_public_repo: {
    message: '분석할 공개 레포가 없어요. GitHub에 공개 레포를 추가한 뒤 다시 시작해주세요.',
    action: 'none',
  },
  unsupported_site: {
    message: '지원하지 않는 공고 사이트예요. 공고 URL을 확인해주세요.',
    action: 'input',
    label: '공고 URL 수정하기',
  },
  jd_fetch_failed: {
    message: '공고를 불러오지 못했어요. 공고 URL을 확인해주세요.',
    action: 'input',
    label: '공고 URL 수정하기',
  },
  jd_extraction_failed: {
    message: '공고 내용을 읽지 못했어요. 공고 URL을 확인해주세요.',
    action: 'input',
    label: '공고 URL 수정하기',
  },
  not_a_job_posting: {
    message: '채용 공고가 아닌 것 같아요. 공고 URL을 확인해주세요.',
    action: 'input',
    label: '공고 URL 수정하기',
  },
  doc_extract_failed: {
    message: '첨부한 포트폴리오를 읽지 못했어요. 다른 파일로 올리거나 빼고 진행해주세요.',
    action: 'input',
    label: '다시 입력하기',
  },
  // ponytail: 대기 시간이 계약에 없어(BE A2) 고정 문구. retryAfter가 생기면 남은 시간을 보여준다.
  rate_limited: {
    message: 'GitHub 요청이 많아 잠시 멈췄어요. 잠시 후 다시 시도해주세요.',
    action: 'input',
    label: '공고 입력으로',
  },
};

const DEFAULT_FAILURE = {
  message: '분석 중 일시적인 문제가 생겼어요. 다시 시도해주세요.',
  action: 'input' as FailureAction,
  label: '다시 시도',
};

export default function AnalysisFailed() {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const postingUrl = postingUrlFrom(location.state);

  const runQuery = useQuery({
    queryKey: queryKeys.analysisRun(runId),
    queryFn: () => api.getAnalysisRun(runId),
    enabled: !!runId,
    // SSE failed로 넘어오면 캐시에는 진행 화면이 받은 running이 남아 있다. 들어올 때마다 새로 읽는다.
    refetchOnMount: 'always',
  });

  const run = runQuery.data;
  // ponytail: BE가 아직 내부 job 코드 token_invalid를 그대로 보낸다. BE가 github_token_invalid로 바꾸면 이 변환을 지운다.
  const failureReason =
    run?.failureReason === 'token_invalid' ? 'github_token_invalid' : run?.failureReason;
  // 실패 사유는 200 응답 안의 값이라 전역 오류 처리가 보지 못한다.
  useEffect(() => refreshMeIfTokenInvalid(failureReason), [failureReason]);
  // 실패하지 않은 run으로 직접 들어오면(링크·기록 이동) 맞는 화면으로 보낸다.
  // 캐시 값으로 보내면 진행 화면과 오가므로 이 화면에서 새로 받은 값만 본다.
  const runStatus = runQuery.isFetchedAfterMount && !runQuery.isFetching ? run?.status : undefined;
  const inputState = location.state;
  useEffect(() => {
    const options = { replace: true, state: inputState };
    if (runStatus === 'running') navigate(`/interview/analyzing/${runId}`, options);
    if (runStatus === 'completed') navigate(`/interview/repos/${runId}`, options);
  }, [runStatus, runId, navigate, inputState]);
  // 진행 화면에서 넘어오면 캐시의 running이 먼저 그려진다. 실패가 확인되기 전에는
  // failureReason이 없어 기본 안내가 잠깐 보였다 바뀌므로, failed일 때만 안내를 그린다.
  const failed = run?.status === 'failed';
  const failure = (failureReason && FAILURE[failureReason]) || DEFAULT_FAILURE;
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

          {!failed && !runQuery.isError && (
            <p role="status" className="text-sm text-muted">
              불러오는 중...
            </p>
          )}
          {runQuery.isError && !failed && (
            <RunLoadError
              error={runQuery.error}
              onRetry={() => void runQuery.refetch()}
              postingUrl={postingUrl}
            />
          )}

          {failed && (
            <div
              role="alert"
              className="rounded-card border border-error-soft bg-error-soft px-4 py-3 text-sm text-error"
            >
              {failure.message}
            </div>
          )}

          {failed && (
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

          {failed && (
            <div className="flex gap-2">
              {failure.action === 'relink' && (
                <a
                  href={`${BASE}/auth/github/link`}
                  className="rounded-md bg-accent px-4 py-2 text-sm font-bold text-white"
                >
                  GitHub 재연동
                </a>
              )}
              {failure.action === 'input' && (
                <button
                  type="button"
                  onClick={() =>
                    navigate('/interview/new', {
                      state: { postingUrl } satisfies AnalysisInputState,
                    })
                  }
                  className="rounded-md bg-accent px-4 py-2 text-sm font-bold text-white"
                >
                  {failure.label}
                </button>
              )}
              <button
                type="button"
                onClick={() => navigate('/home')}
                className="rounded-md border border-line px-4 py-2 text-sm"
              >
                홈으로
              </button>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
