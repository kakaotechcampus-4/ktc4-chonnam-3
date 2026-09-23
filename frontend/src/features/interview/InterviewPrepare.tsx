import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { BASE, api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { isApiError } from '@/types/api';
import type {
  AnswerMode,
  InterviewLastError,
  MeResponse,
  PrepareStepKey,
  PrepareStepStatus,
  WsServerMessage,
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
  /*
    compose_question 실패로 이 화면에도 온다. 준비/진행 구분은 reason이 아니라 step이다
    (frontend/docs/api-spec.md:1222 — 진행 중 오류는 step이 null).
    명세(:195)의 "자동 1회 재시도"는 서버 몫이다. spec/ai/decisions/0010:68이 자동 1회
    재호출을 AI 함수 내부로 정했고, :72는 retry_count를 사용자 수동 retry 횟수로만
    한정한다 — FE가 prepare/retry를 자동으로 부르면 그 값이 오염된다.
    그래서 이 화면은 수동 재시도만 둔다.
  */
  question_failed: '첫 질문을 준비하지 못했어요',
  github_api_rate_limited: 'GitHub 요청 한도를 넘었어요',
  repo_unreachable: '선택한 레포에 접근할 수 없어요',
  github_token_invalid: 'GitHub 연동이 만료됐어요',
};

/** #23 Failure의 reason별 문구. 없는 reason은 기본 문구로 떨어진다. */
const RETRY_REJECTED_MESSAGE: Record<string, string> = {
  prep_in_progress: '이미 다시 준비하고 있어요 · 잠시만 기다려주세요',
  prep_failed: '지금은 다시 시도할 수 없어요 · 상태를 다시 확인할게요',
  session_expired: '면접 세션이 만료됐어요 · 레포를 다시 선택해주세요',
};

const AUDIO_DEVICES = [
  { label: '스피커', hint: '기본 스피커', action: '테스트 재생' },
  // 감지 상태 표시만 두고 테스트 버튼은 없다. 실제 감지는 Sprint 2.
  { label: '마이크', hint: '기본 마이크', badge: '✓ 정상 감지됨' },
];

/** 5b-v2에서 질문을 텍스트로도 볼지. 준비 화면에서 켜 두고 면접 화면이 읽는다. */
export const QUESTION_TEXT_KEY = 'devon.showQuestionText';

function readQuestionText() {
  try {
    return localStorage.getItem(QUESTION_TEXT_KEY) !== 'false';
  } catch {
    return true;
  }
}

/**
 * 재연결 간격. 명세는 "실패해도 계속 재시도"만 정하고 간격은 정하지 않는다.
 * ponytail: 고정 2초. 서버가 오래 죽어 있는 상황이 문제가 되면 지수 백오프로 올린다.
 */
const RECONNECT_DELAY_MS = 2000;

/** 파형은 Sprint 1에서 고정 패턴이다. 입력 레벨 연동은 Sprint 2. */
const IDLE_LEVELS = [
  0.35, 0.6, 0.45, 0.8, 0.5, 0.9, 0.4, 0.7, 0.55, 0.85, 0.45, 0.75, 0.5, 0.65, 0.4, 0.8, 0.55, 0.6,
  0.35, 0.7,
];

export default function InterviewPrepare() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const queryClient = useQueryClient();

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
  const [retrying, setRetrying] = useState(false);
  /** 서버가 재시도를 거절한 reason. api-spec.md #23 Failure. */
  const [retryRejected, setRetryRejected] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  /** 시작을 눌렀지만 서버가 아직 in_progress가 아니거나 조회에 실패했다. */
  const [startFailed, setStartFailed] = useState(false);
  const [showQuestionText, setShowQuestionText] = useState(readQuestionText);
  /** WS를 다시 열기 위한 카운터. 다시 시도와 재연결이 함께 올린다. */
  const [attempt, setAttempt] = useState(0);

  const [wsStatus, setWsStatus] = useState<'connecting' | 'open' | 'reconnecting'>('connecting');

  const socketRef = useRef<WebSocket | null>(null);
  /** recoverable: false면 서버가 세션을 닫는다. 그때는 재연결하지 않는다. */
  const sessionClosedRef = useRef(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /**
   * 예약된 재연결의 일련번호. 끊김이 연달아 나면 이전 GET 응답이 뒤늦게 돌아와도
   * 지난 예약이 attempt를 올리지 못하게 막는다.
   */
  const reconnectSeqRef = useRef(0);

  const status = interview?.status;
  const sessionId = interview?.sessionId;
  // Sprint 1은 항상 'text'라 음성 UI가 뜨지 않는다. Sprint 2에서 'voice'가 추가되면
  // 이 값만으로 마이크·스피커 점검이 살아난다. spec/frontend/features/interview.md:103
  // 스냅샷 도착 전에는 'text'로 본다. 안 그러면 로딩 중 한 프레임 동안 음성 UI가 스친다.
  const answerMode: AnswerMode = interview?.answerMode ?? 'text';

  // status 별 도달 화면. 준비 화면에 머무는 건 preparing / preparing_failed 뿐이다.
  useEffect(() => {
    if (status === 'in_progress') navigate(`/interview/${id}/session`, { replace: true });
    if (status === 'completed') navigate(`/interview/${id}/report`, { replace: true });
  }, [status, id, navigate]);

  // 재시도를 누른 뒤에는 스냅샷이 낡은 값이므로 WS로 받은 상태만 본다.
  const snapshotError = (status === 'preparing_failed' ? interview?.lastError : null) ?? null;
  const displayError = retried ? error : (error ?? snapshotError);
  const displaySteps = steps ?? stepsFromSnapshot(snapshotError?.step);

  useEffect(() => {
    if (!sessionId) return;
    // preparing_failed 진입은 스냅샷으로 충분하다. 다시 시도를 누른 뒤에만 연결한다.
    // attempt는 재연결로도 올라가므로 조건에 쓰지 않는다.
    // 재시도 성공 시 setRetried(true)가 이 effect를 다시 돌려 소켓을 연다 —
    // 새로고침으로 실패 화면에 들어와 소켓이 없는 경우의 연결 경로가 이것이다.
    if (status !== 'preparing' && !(status === 'preparing_failed' && retried)) return;

    let disposed = false;
    const socket = new WebSocket(api.interviewSocketUrl(sessionId));
    socketRef.current = socket;

    socket.onopen = () => {
      setWsStatus('open');
    };

    socket.onmessage = (event) => {
      let message: WsServerMessage;
      try {
        message = JSON.parse(event.data as string) as WsServerMessage;
      } catch {
        // 깨진 프레임 하나 때문에 이후 메시지 처리까지 죽지 않게 한다.
        return;
      }

      if (message.type === 'prepareStep') {
        setSteps((prev) => ({ ...(prev ?? INITIAL_STEPS), [message.key]: message.status }));
        // 단계가 다시 도는 게 보이면 거절 안내도 무효다. prep_in_progress로 거절당한 뒤
        // 서버가 실제로 진행하는 경우가 여기다.
        setRetryRejected(null);
        // 재연결 시 이전 시도의 error가 늦게 도착하면 방금 지운 배너가 되살아난다.
        // 단계가 다시 도는 게 보이면 이전 오류는 무효다. 같은 단계의 failed 뒤에는
        // 곧바로 error가 따라오므로 실패 표시가 지워지지는 않는다.
        setError(null);
      } else if (message.type === 'prepareCompleted') {
        setReady(true);
      } else if (message.type === 'error') {
        if (!message.recoverable) sessionClosedRef.current = true;
        setError({
          reason: message.reason,
          code: message.code,
          step: message.step,
          recoverable: message.recoverable,
          occurredAt: message.occurredAt,
        });
      }
    };

    socket.onclose = () => {
      // close 이벤트는 비동기라 새 소켓이 이미 socketRef에 들어온 뒤 도착할 수 있다.
      // 자기 소켓일 때만 비운다. 아니면 살아 있는 연결의 참조를 지워, 다시 시도가
      // OPEN 분기 대신 재연결 경로를 타면서 멀쩡한 소켓을 한 번 더 끊는다.
      if (socketRef.current === socket) socketRef.current = null;
      if (disposed || sessionClosedRef.current) return;

      setWsStatus('reconnecting');
      /**
       * 재연결 전에 GET /interviews/{id}를 먼저 호출한다. 이 요청이 401 인터셉터를 타면서
       * 토큰이 갱신된다. 순서를 바꾸면 만료 토큰으로 핸드셰이크를 시도해 401이 반복된다.
       * 재연결 실패는 세션 상태를 바꾸지 않는다 — 될 때까지 다시 시도한다.
       */
      const seq = ++reconnectSeqRef.current;
      reconnectTimerRef.current = setTimeout(() => {
        void queryClient.refetchQueries({ queryKey: queryKeys.interview(id) }).finally(() => {
          if (reconnectSeqRef.current !== seq) return;
          setAttempt((count) => count + 1);
        });
      }, RECONNECT_DELAY_MS);
    };

    return () => {
      disposed = true;
      // 화면을 떠나거나 새 연결로 넘어갈 때 예약된 재연결을 남기지 않는다.
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      socket.close();
    };
  }, [sessionId, status, attempt, retried, id, queryClient]);

  /**
   * prepareCompleted는 WS로만 오므로 React Query 캐시의 status는 아직 preparing이다.
   * 진행 화면이 같은 쿼리키를 읽으면 낡은 값을 보고 준비 화면으로 되돌린다.
   * 이동 전에 다시 조회해 in_progress를 확인한다.
   */
  const handleStart = async () => {
    setStarting(true);
    setStartFailed(false);

    const { data } = await refetchInterview();
    if (data?.status === 'in_progress') {
      navigate(`/interview/${id}/session`);
      return;
    }

    setStarting(false);
    setStartFailed(true);
  };

  /**
   * 준비 재시도는 REST다 (api-spec.md #23, spec/ai/decisions/0010:32).
   * 소켓은 닫지 않는다 — 열려 있으면 그대로 두고, 없으면 응답을 확인한 뒤 연다.
   * 진행 상황은 이 응답이 아니라 WS prepareStep 으로 온다.
   */
  const handleRetry = async () => {
    setRetryRejected(null);
    setRetrying(true);
    try {
      await api.retryPrepare(id);
    } catch (e) {
      const reason = isApiError(e) ? e.error.reason : 'unknown_error';
      setRetryRejected(reason);
      setRetrying(false);
      // 이미 재실행 중이면 그대로 진행을 기다린다. 그 외에는 서버 상태를 다시 읽는다.
      if (reason !== 'prep_in_progress') void refetchInterview();
      return;
    }
    setRetrying(false);
    setError(null);
    setReady(false);
    // retried는 소켓을 여는 트리거다. 이미 열려 있으면 올리지 않는다 — effect deps가
    // 바뀌면 cleanup이 멀쩡한 소켓을 닫고 새로 열어 그 사이 prepareStep을 놓친다.
    // 소켓이 열려 있다는 건 status가 preparing이라는 뜻이라 snapshotError가 null이고,
    // displayError는 retried 값과 무관하게 error가 된다.
    if (socketRef.current?.readyState !== WebSocket.OPEN) setRetried(true);
    // 성공한 단계는 서버가 재실행하지 않는다. 실패 단계만 pending으로 되돌린다.
    setSteps(
      Object.fromEntries(
        Object.entries(displaySteps).map(([key, value]) => [
          key,
          value === 'failed' ? 'pending' : value,
        ]),
      ) as StepMap,
    );
  };

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
          className="h-10 text-[13px] font-bold text-muted"
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

      {/*
        연결이 끊겨도 세션 상태는 바꾸지 않는다. 안내만 띄우고 재연결을 계속 시도한다.
        실패 배너가 떠 있으면 숨긴다. 재연결 중 조회한 상태가 preparing_failed면 위 가드가
        소켓을 다시 열지 않아 wsStatus가 reconnecting으로 남고, 두 메시지가 함께 굳는다.
      */}
      {!displayError && wsStatus === 'reconnecting' && (
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
          {/*
            고객센터 페이지는 추후 추가 예정이다. 지금은 /help 라우트가 없어
            링크로 두면 routes.tsx:27의 * 규칙에 걸려 홈으로 튄다. 같은 안내를 쓰는
            MyPage.tsx:203도 텍스트다 (spec/frontend/features/mypage.md:33 "API 없음").
            ponytail: 페이지가 생기면 <Link to="/help">고객센터</Link>로 되돌린다.
            MyPage 쪽도 같이 바꾼다.
          */}
          {displayError.code} · {displayError.occurredAt} · 선택한 레포와 공고는 저장되어 있어요.
          문의는 고객센터로 부탁드려요.
        </p>
      )}

      {/*
        마이크 · 스피커 점검. Sprint 2(음성) 범위라 Sprint 1 화면에는 뜨지 않는다.
        (spec/frontend/features/interview.md:17) 실제 장치 접근·재생·녹음도 Sprint 2다.
      */}
      {answerMode !== 'text' && (
        <div className="border-t border-line-soft pt-5">
          <h2 className="text-[13px] font-bold">마이크 · 스피커 점검</h2>

          {AUDIO_DEVICES.map(({ label, hint, action, badge }) => (
            <div key={label} className="mt-4 flex items-center gap-3">
              <div className="flex-1">
                <p className="text-[13px] font-bold">{label}</p>
                <p className="text-[11px] text-muted">{hint}</p>
              </div>
              {badge ? (
                <span className="rounded-full bg-accent-soft px-3 py-1.5 text-[12px] font-bold text-accent">
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
      )}

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
          {retryRejected && (
            <p className="text-[11px] font-bold text-error">
              {RETRY_REJECTED_MESSAGE[retryRejected] ?? '다시 시도하지 못했어요 · 잠시 후 눌러주세요'}
            </p>
          )}
          {/*
            recoverable: false면 재시도 없이 레포 재선택만 남긴다.
            session_expired는 세션이 사라진 것이라 재시도 자체가 불가능하다 (#23 Failure).
          */}
          {displayError.recoverable && retryRejected !== 'session_expired' && (
            <button
              type="button"
              disabled={retrying}
              onClick={() => void handleRetry()}
              className="h-12 rounded-lg bg-accent text-sm font-bold text-surface disabled:bg-line-soft disabled:text-muted"
            >
              {retrying ? '다시 시도하는 중...' : '다시 시도'}
            </button>
          )}
          {/*
            github_token_invalid는 레포를 다시 골라도 같은 오류로 돌아온다.
            명세(spec/frontend/features/interview.md:202)대로 GitHub 재연동으로 보낸다.
            OAuth 리다이렉트라 SPA 라우팅이 아닌 <a>가 맞다 (Home.tsx:35과 같은 경로).
          */}
          {displayError.reason === 'github_token_invalid' ? (
            <a
              href={`${BASE}/auth/github/link`}
              className="flex h-12 items-center justify-center rounded-lg bg-accent text-sm font-bold text-surface"
            >
              GitHub 다시 연동하기
            </a>
          ) : (
            <button
              type="button"
              onClick={() => navigate(`/interview/repos/${interview!.runId}`)}
              className={
                displayError.recoverable
                  ? 'h-10 text-[13px] font-bold text-muted'
                  : 'h-12 rounded-lg bg-accent text-sm font-bold text-surface'
              }
            >
              레포 다시 선택하기
            </button>
          )}
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
      <main className="flex flex-1 flex-col items-center px-7 pb-7 pt-6">
        <div className="flex w-[440px] max-w-full flex-col gap-4 py-10">{children}</div>
      </main>
      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}
