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
import { isApiError, type StepKey, type StepStatus } from '@/types/api';

type FailureAction = 'relink' | 'input' | 'none';

/** tips는 경고 아래에 보여 줄 기준·해결 방법이다(짧은 제목 + 설명). 경고 문구는 한 줄로 둔다. */
type FailureGuide = {
  message: string;
  action: FailureAction;
  label?: string;
  tips?: { title: string; body: string }[];
};

/**
 * failureReason 값은 frontend/docs/api-spec.md의 failureReason 표를 따른다. 없는 값은 DEFAULT_FAILURE.
 * failureReason은 job 코드라 HTTP reason과 다르다. GitHub 토큰 무효는 job 코드 token_invalid다(#144).
 * input은 공고 입력 화면에 이전 URL을 채워 보낸다. 다시 분석은 사용자가 그 화면에서 시작한다.
 */
const FAILURE: Record<string, FailureGuide> = {
  token_invalid: {
    message: 'GitHub 연동이 만료됐어요. 다시 연동한 뒤 분석해주세요.',
    action: 'relink',
  },
  // 공개 레포가 있어도 기준에 맞는 레포가 없으면 같은 사유가 온다. 기준과 포함 방법을 함께 안내한다.
  // 수집: 본인 소유 public만(BE github/client.py affiliation=owner). 제외: fork·archived·언어 없음·
  // 작은 크기(github/base.py filter_reason). 포트폴리오에 언급된 레포는 제외를 건너뛴다(BE 결정 0001).
  // 레포 목록은 로그인할 때만 다시 수집한다(auth/service.py).
  no_public_repo: {
    message: '분석할 수 있는 레포를 찾지 못했어요.',
    action: 'none',
    tips: [
      {
        title: '분석 대상',
        body: '내 계정이 소유한 공개 레포만 분석해요. fork·보관·조직 레포와 코드가 거의 없는 레포는 빠져요.',
      },
      {
        title: '빠진 레포를 넣으려면',
        body: '포트폴리오에 레포 주소를 적어 첨부해주세요. 조직 레포는 내 계정으로 fork한 주소를 적어주세요.',
      },
      { title: '레포를 새로 올렸다면', body: '다시 로그인한 뒤 시작해주세요.' },
    ],
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

const DEFAULT_FAILURE: FailureGuide = {
  message: '분석 중 일시적인 문제가 생겼어요. 다시 시도해주세요.',
  action: 'input',
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
  const failureReason = run?.failureReason;
  // 실패 사유는 200 응답 안의 값이라 전역 오류 처리가 보지 못한다.
  // refreshMeIfTokenInvalid는 HTTP reason(github_token_invalid) 기준이라 job 코드 token_invalid를 변환해 넘긴다.
  useEffect(
    () =>
      refreshMeIfTokenInvalid(failureReason === 'token_invalid' ? 'github_token_invalid' : null),
    [failureReason],
  );
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
  // DB partial run은 API에서 failed로 보이지만 성공한 저장소의 결과는 조회된다(analysis-run.md 부분 실패).
  // 상태값만으로는 구분할 수 없어 결과 조회로 판단한다. 진짜 실패한 run은 409 not_ready다.
  const resultQuery = useQuery({
    queryKey: queryKeys.analysisResult(runId),
    queryFn: () => api.getAnalysisRunResult(runId),
    enabled: failed,
    retry: false,
  });
  const hasSucceededRepos = !!resultQuery.data?.repositories.some((r) => r.status === 'succeeded');
  // 면접을 진행할 수 있는 run이라 실패 화면을 보이지 않고 레포 선택으로 보낸다(analysis.md 부분 실패).
  useEffect(() => {
    if (hasSucceededRepos)
      navigate(`/interview/repos/${runId}`, { replace: true, state: inputState });
  }, [hasSucceededRepos, runId, navigate, inputState]);
  // 409 not_ready는 결과가 없는 실패 run이다. 그 밖의 조회 오류(5xx·네트워크)는 부분 실패 여부를 모르는
  // 상태라 버튼을 숨긴 채 끝내지 않고 다시 불러오게 한다.
  const resultLoadFailed =
    resultQuery.isError &&
    !(isApiError(resultQuery.error) && resultQuery.error.error.reason === 'not_ready');
  // 결과 조회 전에 그리면 부분 실패 run에서 실패 안내가 보였다가 레포 선택으로 넘어가므로,
  // 조회가 끝나고 실패가 확정된 뒤에 제목·안내·체크리스트·버튼을 그린다.
  const ready = failed && !resultQuery.isPending && !hasSucceededRepos;

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header />

      <main className="flex flex-1 flex-col items-center px-7 pb-7 pt-6">
        <div className="flex w-[380px] max-w-full flex-col gap-4 py-14">
          <p className="text-[11px] font-bold text-accent">모의면접 · 분석 중</p>

          {(ready || runQuery.isError) && (
            <div className="flex items-center gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-error-soft text-sm font-bold text-error">
                !
              </span>
              <h1 className="flex-1 text-base font-bold">GitHub 레포를 분석하지 못했어요</h1>
            </div>
          )}

          {!ready && !runQuery.isError && (
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

          {ready && (
            <div
              role="alert"
              className="rounded-card border border-error-soft bg-error-soft px-4 py-3 text-sm text-error"
            >
              {failure.message}
            </div>
          )}
          {ready && failure.tips && (
            // 리포트의 요구사항 안내 박스(Report.tsx)와 같은 bg-paper 박스로 맞춘다.
            <ul
              aria-label="분석 기준과 해결 방법"
              className="flex flex-col gap-3 break-keep rounded-lg bg-paper px-4 py-3"
            >
              {failure.tips.map((tip) => (
                <li key={tip.title} className="flex flex-col gap-0.5">
                  <p className="text-[13px] font-bold">{tip.title}</p>
                  <p className="text-[13px] leading-relaxed text-muted">{tip.body}</p>
                </li>
              ))}
            </ul>
          )}
          {ready && resultLoadFailed && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-error">분석 결과를 불러오지 못했어요.</p>
              <button
                type="button"
                onClick={() => void resultQuery.refetch()}
                className="self-start rounded-md border border-line px-4 py-2 text-sm"
              >
                결과 다시 불러오기
              </button>
            </div>
          )}

          {ready && (
            <ul className="flex flex-col gap-3">
              {STEP_GROUPS.map((group) => {
                const status = groupStatus(group.keys, stepStatus);
                if (status === 'skipped') return null;
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

          {ready && (
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
                // 재연동·다시 입력 같은 주 버튼이 없으면 홈으로가 유일한 출구라 주 버튼 색으로 둔다.
                className={
                  failure.action === 'none'
                    ? 'rounded-md bg-accent px-4 py-2 text-sm font-bold text-white'
                    : 'rounded-md border border-line px-4 py-2 text-sm'
                }
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
