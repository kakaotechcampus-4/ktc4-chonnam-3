import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { useInterviewSocket } from '@/features/interview/useInterviewSocket';
import { QUESTION_TEXT_KEY, readQuestionText } from '@/features/interview/questionText';
import type {
  InterviewLastError,
  MeResponse,
  PrepareStepKey,
  PrepareStepStatus,
} from '@/types/api';

/** 실행 순서는 spec/frontend/features/interview.md의 4단계를 따른다. */
const PREPARE_STEPS: { key: PrepareStepKey; label: string }[] = [
  { key: 'analyze_repo', label: '레포 · JD 분석' },
  { key: 'build_persona', label: '면접관 페르소나 준비' },
  { key: 'set_criteria', label: '답변 평가 기준 설정' },
  { key: 'compose_question', label: '첫 질문 구성' },
];

const STATUS_SUFFIX: Record<PrepareStepStatus, string> = {
  pending: '',
  running: ' 중',
  completed: ' 완료',
  failed: ' 실패',
};

type StepMap = Record<PrepareStepKey, PrepareStepStatus>;

const INITIAL_STEPS: StepMap = {
  analyze_repo: 'pending',
  build_persona: 'pending',
  set_criteria: 'pending',
  compose_question: 'pending',
};

/**
 * 새로고침 복구용 체크리스트. preparing_failed 스냅샷의 lastError.step 하나로
 * 실패 단계 이전은 completed, 이후는 pending 그대로 복원한다. WS 재연결이 필요 없다.
 */
function stepsFromSnapshot(failedStep: PrepareStepKey | null | undefined): StepMap {
  const failedAt = PREPARE_STEPS.findIndex((step) => step.key === failedStep);
  if (failedAt < 0) return INITIAL_STEPS;
  return Object.fromEntries(
    PREPARE_STEPS.map((step, index) => [
      step.key,
      index < failedAt ? 'completed' : index === failedAt ? 'failed' : 'pending',
    ]),
  ) as StepMap;
}

/** 실패 제목은 error.reason 별로 갈린다. code·occurredAt은 제목 아래에 그대로 노출한다. */
const FAILURE_TITLE: Record<string, string> = {
  repo_analyze_failed: '레포를 분석하지 못했어요',
  persona_build_failed: '면접관 페르소나를 준비하지 못했어요',
  criteria_set_failed: '답변 평가 기준을 만들지 못했어요',
  question_gen_timeout: '첫 질문을 준비하지 못했어요',
  question_failed: '첫 질문을 준비하지 못했어요',
  github_api_rate_limited: 'GitHub 요청 한도를 넘었어요',
  repo_unreachable: '선택한 레포에 접근할 수 없어요',
  github_token_invalid: 'GitHub 연동이 만료됐어요',
};

const AUDIO_DEVICES = [
  { label: '스피커', hint: '기본 스피커', action: '테스트 재생' },
  // 실제 장치 감지는 Sprint 2다. 감지했다고 단언하지 않는다.
  { label: '마이크', hint: '기본 마이크', badge: '점검 예정' },
];

/** 파형은 Sprint 1에서 고정 패턴이다. 입력 레벨 연동은 Sprint 2. */
const IDLE_LEVELS = [
  0.35, 0.6, 0.45, 0.8, 0.5, 0.9, 0.4, 0.7, 0.55, 0.85, 0.45, 0.75, 0.5, 0.65, 0.4, 0.8, 0.55, 0.6,
  0.35, 0.7,
];

export default function InterviewPrepare() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: me } = useQuery({ queryKey: queryKeys.me, queryFn: api.getMe });
  const {
    data: interview,
    isError: interviewFailed,
    refetch: refetchInterview,
  } = useQuery({
    queryKey: queryKeys.interview(id),
    queryFn: () => api.getInterview(id),
    enabled: !!id,
  });

  // null 이면 아직 WS로 받은 단계가 없다는 뜻이고, 그때는 스냅샷을 그대로 쓴다.
  const [steps, setSteps] = useState<StepMap | null>(null);
  const [error, setError] = useState<InterviewLastError | null>(null);
  const [retried, setRetried] = useState(false);
  const [ready, setReady] = useState(false);
  const [starting, setStarting] = useState(false);
  /** 시작을 눌렀지만 서버가 아직 in_progress가 아니거나 조회에 실패했다. */
  const [startFailed, setStartFailed] = useState(false);
  const [showQuestionText, setShowQuestionText] = useState(readQuestionText);

  const status = interview?.status;
  const sessionId = interview?.sessionId;

  // status 별 도달 화면. 준비 화면에 머무는 건 preparing / preparing_failed 뿐이다.
  useEffect(() => {
    if (status === 'in_progress') navigate(`/interview/${id}/session`, { replace: true });
    if (status === 'completed') navigate(`/interview/${id}/report`, { replace: true });
  }, [status, id, navigate]);

  // 재시도를 누른 뒤에는 스냅샷이 낡은 값이므로 WS로 받은 상태만 본다.
  const snapshotError = (status === 'preparing_failed' ? interview?.lastError : null) ?? null;
  const displayError = retried ? error : (error ?? snapshotError);
  const displaySteps = steps ?? stepsFromSnapshot(snapshotError?.step);

  const { wsStatus, send } = useInterviewSocket({
    interviewId: id,
    sessionId,
    // preparing_failed 진입은 스냅샷으로 충분하다. 다시 시도를 누른 뒤에만 연결한다.
    enabled: status === 'preparing' || (status === 'preparing_failed' && retried),
    onMessage: (message) => {
      if (message.type === 'prepareStep') {
        setSteps((prev) => ({ ...(prev ?? INITIAL_STEPS), [message.key]: message.status }));
      } else if (message.type === 'prepareCompleted') {
        setReady(true);
      } else if (message.type === 'error') {
        setError({
          reason: message.reason,
          code: message.code,
          step: message.step,
          recoverable: message.recoverable,
          occurredAt: message.occurredAt,
        });
      }
    },
  });

  const handleRetry = () => {
    setError(null);
    setRetried(true);
    setReady(false);
    // 성공한 단계는 서버가 재실행하지 않는다. 실패 단계만 pending으로 되돌린다.
    setSteps(
      Object.fromEntries(
        Object.entries(displaySteps).map(([key, value]) => [
          key,
          value === 'failed' ? 'pending' : value,
        ]),
      ) as StepMap,
    );
    // 멱등한 메시지라 연결이 끊겨 있으면 재연결 후 보내도 안전하다.
    send({ type: 'prepareRetry' }, { queue: true });
  };

  /**
   * prepareCompleted는 WS로만 왔고 REST 캐시의 status는 아직 preparing이다.
   * 진행 화면은 그 캐시를 그대로 읽으므로, 먼저 갱신해 두지 않으면 준비 화면으로 되튕긴다.
   * refetch는 실패해도 throw하지 않으므로 결과의 status를 직접 확인한다.
   */
  async function handleStart() {
    setStarting(true);
    setStartFailed(false);

    const { data } = await refetchInterview();
    if (data?.status === 'in_progress') {
      navigate(`/interview/${id}/session`);
      return;
    }

    setStarting(false);
    setStartFailed(true);
  }

  if (interviewFailed) {
    return (
      <Shell me={me}>
        <p className="text-[11px] font-bold text-accent">모의면접 · 면접 준비</p>
        <h1 className="text-base font-bold">면접 정보를 불러오지 못했어요</h1>
        <p className="text-[13px] text-muted">
          면접이 삭제됐거나 주소가 잘못됐을 수 있어요. 잠시 후 다시 시도해주세요.
        </p>
        <button
          type="button"
          onClick={() => void refetchInterview()}
          className="h-12 rounded-lg bg-accent text-sm font-bold text-surface"
        >
          다시 불러오기
        </button>
        <button
          type="button"
          onClick={() => navigate('/home')}
          className="h-11 rounded-lg border border-line text-[13px] font-bold text-muted"
        >
          홈으로
        </button>
      </Shell>
    );
  }

  if (status === 'abandoned') {
    return (
      <Shell me={me}>
        <p className="text-[11px] font-bold text-accent">모의면접 · 면접 준비</p>
        <h1 className="text-base font-bold">중단된 면접이에요</h1>
        <button
          type="button"
          onClick={() => navigate('/home')}
          className="h-11 rounded-lg bg-accent text-sm font-bold text-surface"
        >
          홈으로
        </button>
      </Shell>
    );
  }

  return (
    <Shell me={me}>
      <p className="text-[11px] font-bold text-accent">모의면접 · 면접 준비</p>

      <div className="flex items-center gap-3">
        {displayError ? (
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-error-soft text-sm font-bold text-error">
            !
          </span>
        ) : (
          <span className="h-7 w-7 shrink-0 animate-spin rounded-full border-[3px] border-accent-soft border-t-accent" />
        )}
        <h1 className="flex-1 text-base font-bold">
          {displayError
            ? (FAILURE_TITLE[displayError.reason] ?? '면접 준비에 실패했어요')
            : '첫 질문을 준비하고 있어요'}
        </h1>
      </div>

      <ul className="flex flex-col gap-3">
        {PREPARE_STEPS.map(({ key, label }) => {
          const stepStatus = displaySteps[key];
          return (
            <li key={key} className="flex items-center gap-2.5">
              {stepStatus === 'completed' && (
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent">
                  ✓
                </span>
              )}
              {stepStatus === 'running' && (
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent">
                  ···
                </span>
              )}
              {stepStatus === 'failed' && (
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-error-soft text-[10px] font-bold text-error">
                  !
                </span>
              )}
              {stepStatus === 'pending' && (
                <span className="h-5 w-5 shrink-0 rounded-full bg-line-soft" />
              )}
              <span
                className={
                  stepStatus === 'failed'
                    ? 'flex-1 text-[13px] font-bold text-error'
                    : stepStatus === 'running'
                      ? 'flex-1 text-[13px] font-bold'
                      : stepStatus === 'completed'
                        ? 'flex-1 text-[13px]'
                        : 'flex-1 text-[13px] text-muted'
                }
              >
                {label}
                {STATUS_SUFFIX[stepStatus]}
              </span>
            </li>
          );
        })}
      </ul>

      {/* 연결이 끊겨도 세션 상태는 바꾸지 않는다. 안내만 띄우고 재연결을 계속 시도한다. */}
      {wsStatus === 'reconnecting' && (
        <p className="text-[11px] font-bold text-error">연결이 끊겼어요 · 다시 연결하는 중이에요</p>
      )}

      {!displayError && wsStatus !== 'reconnecting' && (
        <p className="text-[11px] text-muted">
          보통 1~2분 정도 걸려요 · 기다리는 동안 마이크와 스피커를 확인해주세요
        </p>
      )}

      {/* code·occurredAt은 표시용 식별자라 그대로 노출한다. */}
      {displayError && (
        <p className="text-[11px] text-muted">
          {displayError.code} · {displayError.occurredAt} · 선택한 레포와 공고는 저장되어 있어요.{' '}
          <a href="/help" className="underline">
            고객센터
          </a>
        </p>
      )}

      {/*
        마이크 · 스피커 점검. 실제 장치 접근·재생·녹음은 Sprint 2(음성) 범위다.
        Sprint 1은 answerMode가 항상 'text'라 화면만 두고 버튼은 비활성으로 남긴다.
      */}
      <div className="border-t border-line-soft pt-5">
        <h2 className="text-[13px] font-bold">마이크 · 스피커 점검</h2>

        {AUDIO_DEVICES.map(({ label, hint, action, badge }) => (
          <div key={label} className="mt-4 flex items-center gap-3">
            <div className="flex-1">
              <p className="text-[13px] font-bold">{label}</p>
              <p className="text-[11px] text-muted">{hint}</p>
            </div>
            {badge ? (
              <span className="rounded-full bg-paper px-3 py-1.5 text-[12px] font-bold text-muted">
                {badge}
              </span>
            ) : (
              <button
                type="button"
                disabled
                className="h-9 rounded-lg border border-line px-4 text-[12px] font-bold text-muted"
              >
                {action}
              </button>
            )}
          </div>
        ))}

        <div className="mt-4 flex h-12 items-center justify-center gap-1 rounded-card border border-line-soft">
          {IDLE_LEVELS.map((level, index) => (
            <span
              key={index}
              className="w-[3px] rounded-full bg-accent"
              style={{ height: `${Math.round(level * 28)}px` }}
            />
          ))}
        </div>
      </div>

      {/* 준비 중·실패 어느 쪽이든 항상 보인다. 값은 5b-v2가 읽는다. */}
      <label className="flex items-center gap-3">
        <span className="flex-1">
          <span className="block text-[13px] font-bold">질문 텍스트 표시</span>
          <span className="block text-[11px] text-muted">
            면접 중에도 질문을 텍스트로 볼 수 있어요
          </span>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={showQuestionText}
          onChange={(event) => {
            setShowQuestionText(event.target.checked);
            try {
              localStorage.setItem(QUESTION_TEXT_KEY, String(event.target.checked));
            } catch {
              /* 시크릿 창 등에서 저장이 막히면 이번 세션에만 적용한다. */
            }
          }}
          className="h-6 w-11 shrink-0 appearance-none rounded-full bg-line-soft transition-colors before:ml-0.5 before:block before:h-5 before:w-5 before:translate-y-0.5 before:rounded-full before:bg-surface before:transition-transform checked:bg-accent checked:before:translate-x-5"
        />
      </label>

      {displayError ? (
        <div className="flex flex-col gap-2">
          {/* recoverable: false면 재시도 없이 레포 재선택만 남긴다. */}
          {displayError.recoverable && (
            <button
              type="button"
              onClick={handleRetry}
              className="h-12 rounded-lg bg-accent text-sm font-bold text-surface"
            >
              다시 시도
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate(`/interview/repos/${interview!.runId}`)}
            className={
              displayError.recoverable
                ? 'h-11 rounded-lg border border-line text-[13px] font-bold text-muted'
                : 'h-12 rounded-lg bg-accent text-sm font-bold text-surface'
            }
          >
            레포 다시 선택하기
          </button>
        </div>
      ) : (
        <>
          {startFailed && (
            <p className="text-[11px] font-bold text-error">
              면접을 열지 못했어요 · 잠시 후 다시 눌러주세요
            </p>
          )}
          <button
            type="button"
            disabled={!ready || starting}
            onClick={() => void handleStart()}
            className="h-12 rounded-lg bg-accent text-sm font-bold text-surface disabled:bg-line-soft disabled:text-muted"
          >
            {starting ? '면접을 여는 중...' : '면접 시작하기'}
          </button>
        </>
      )}
    </Shell>
  );
}

function Shell({ me, children }: { me?: MeResponse; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header
        active="interview"
        githubLinked={me?.githubLinked}
        name={me?.name}
        avatarUrl={me?.avatarUrl ?? undefined}
      />
      <main className="flex flex-1 flex-col items-center justify-center px-7 py-6">
        <div className="flex w-full max-w-md flex-col gap-4">{children}</div>
      </main>
      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}
