import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { BASE, api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { PERSONA_IMAGES, PERSONA_LABELS, PERSONA_ORDER } from '@/shared/persona';
import { useInterviewSocket } from '@/features/interview/useInterviewSocket';
import { useQuestionAudio } from '@/features/interview/useQuestionAudio';
import { MAX_ANSWER_MS, useAnswerRecorder } from '@/features/interview/useAnswerRecorder';
import { QUESTION_TEXT_KEY, readQuestionText } from '@/features/interview/questionText';
import type { InterviewLastError, MeResponse, Persona } from '@/types/api';

/** 진행 중 오류 문구. 답변 실패(stt_failed·answer_rejected)는 턴 안에서 따로 안내한다. */
const ERROR_MESSAGE: Record<string, string> = {
  question_failed: '다음 질문을 만들지 못했어요. 잠시만 기다려주세요.',
  repo_unreachable: '레포에 접근할 수 없어 면접을 이어갈 수 없어요.',
  github_token_invalid: 'GitHub 연동이 만료돼 면접을 이어갈 수 없어요.',
};

/** 30초간 다른 메시지가 없으면 근거 확인 배너를 내린다. */
const EVIDENCE_TIMEOUT_MS = 30_000;

/** answerEnd 뒤 이 시간 안에 transcript가 없으면 스냅샷으로 저장 여부를 확인한다. */
const TRANSCRIPT_TIMEOUT_MS = 30_000;

/** 녹음 중 새로고침을 알아채기 위한 표식. 녹음 시작에 남기고 제출·실패·재시도에 지운다. */
const RECORDING_KEY = 'devon.recordingAnswer';

const TIPS = [
  '답변 시작을 누르면 녹음이 시작돼요.',
  '답변 끝내기를 누르면 답변이 제출돼요.',
  '질문을 다시 들으려면 면접관에게 다시 들려달라고 답변하셔도 좋아요.',
];

type LiveQuestion = {
  persona: Persona;
  text: string;
  turn: number;
  mainIndex: number;
  followUpDepth: number;
  audioUrl: string | null;
};

/** 한 턴의 답변 단계. spec/frontend/designs/2026-10-05-voice-interview.md "턴 상태". */
type AnswerPhase = 'listening' | 'recording' | 'transcribing' | 'submitted' | 'failed';
type Failure = 'disconnected' | 'stt' | 'empty' | 'rejected' | 'micLost' | 'micUnavailable';
type AnswerState = {
  turn: number;
  phase: AnswerPhase;
  partial: string;
  final: string | null;
  failure: Failure | null;
};

const FAILURE_MESSAGE: Record<Failure, string> = {
  disconnected: '연결이 끊겨 답변이 저장되지 않았어요 · 다시 답변해주세요',
  stt: '음성을 글로 바꾸지 못했어요 · 다시 답변해주세요',
  empty: '목소리가 인식되지 않았어요 · 마이크를 확인하고 다시 답변해주세요',
  rejected: '답변을 저장하지 못했어요 · 다시 답변해주세요',
  micLost: '마이크 연결이 끊겼어요 · 확인 후 다시 답변해주세요',
  micUnavailable: '마이크를 사용할 수 없어요 · 브라우저의 마이크 권한과 연결을 확인해주세요',
};

function formatRemaining(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function markRecording(interviewId: string, turn: number | null) {
  try {
    if (turn === null) sessionStorage.removeItem(RECORDING_KEY);
    else sessionStorage.setItem(RECORDING_KEY, JSON.stringify({ interviewId, turn }));
  } catch {
    /* 저장이 막히면 새로고침 안내만 빠진다. */
  }
}

/** 녹음 중 새로고침된 턴. 지우지 않는다 — StrictMode가 초기값 함수를 두 번 부른다. */
function readInterruptedTurn(interviewId: string): number | null {
  try {
    const raw = sessionStorage.getItem(RECORDING_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as { interviewId?: string; turn?: number };
    return value.interviewId === interviewId && typeof value.turn === 'number' ? value.turn : null;
  } catch {
    return null;
  }
}

export default function InterviewScreen() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: me } = useQuery({ queryKey: queryKeys.me, queryFn: api.getMe });
  const {
    data: interview,
    isError: interviewFailed,
    isFetching,
    dataUpdatedAt,
    refetch: refetchInterview,
  } = useQuery({
    queryKey: queryKeys.interview(id),
    queryFn: () => api.getInterview(id),
    enabled: !!id,
  });

  const [liveQuestion, setLiveQuestion] = useState<LiveQuestion | null>(null);
  /** question을 받을 때마다 올린다. 같은 턴이 다시 오면(다시 듣기) 음성을 처음부터 재생한다. */
  const [playKey, setPlayKey] = useState(0);
  /** 전사 대기 확인 조회가 실패했을 때 올려 같은 확인을 한 주기 더 돌린다. */
  const [recheck, setRecheck] = useState(0);
  /** 녹음 중 새로고침이었다면 그 턴을 끊김 실패로 시작한다. */
  const [answer, setAnswer] = useState<AnswerState | null>(() => {
    const turn = readInterruptedTurn(id);
    return turn === null
      ? null
      : { turn, phase: 'failed', partial: '', final: null, failure: 'disconnected' };
  });
  /** 녹음 중인 턴. 녹음기 콜백이 리렌더보다 먼저 와도 맞는 턴으로 보내게 한다. */
  const recordingTurnRef = useRef<number | null>(null);
  const [thinking, setThinking] = useState(false);
  const [evidence, setEvidence] = useState<{ repository: string; file: string } | null>(null);
  const [error, setError] = useState<InterviewLastError | null>(null);
  const [leaveModalOpen, setLeaveModalOpen] = useState(false);
  const leaveDialogRef = useRef<HTMLDialogElement>(null);
  const [showQuestionText, setShowQuestionText] = useState(readQuestionText);
  /** 1초마다 흐르는 시계. 남은 시간과 녹음 경과 시간을 이 값으로 계산한다. */
  const [now, setNow] = useState(() => Date.now());

  const status = interview?.status;

  /**
   * 준비 화면에서 막 넘어온 직후에는 캐시의 status가 아직 preparing이다.
   * 갱신이 끝나기 전에 판단하면 준비 화면으로 되튕겨 왕복이 생긴다.
   */
  useEffect(() => {
    if (isFetching) return;
    if (status === 'preparing' || status === 'preparing_failed') {
      navigate(`/interview/${id}/prepare`, { replace: true });
    }
    if (status === 'completed') navigate(`/interview/${id}/report`, { replace: true });
  }, [status, isFetching, id, navigate]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const dialog = leaveDialogRef.current;
    if (!dialog) return;
    if (leaveModalOpen) dialog.showModal();
    else dialog.close();
  }, [leaveModalOpen]);

  /** 실패·끊김 처리가 녹음기를 멈추기 위한 참조. 녹음기는 소켓 아래에서 만들어진다. */
  const recorderRef = useRef<{ cancel: () => void } | null>(null);

  /** 지금 턴의 답변을 실패로 돌린다. 녹음 중이면 마이크를 닫고 표식도 지운다. */
  const fail = (failure: Failure) => {
    recorderRef.current?.cancel();
    markRecording(id, null);
    setAnswer((prev) => (prev ? { ...prev, phase: 'failed', failure } : prev));
  };

  const {
    wsStatus,
    send,
    sendBinary,
    close: closeSocket,
  } = useInterviewSocket({
    interviewId: id,
    sessionId: interview?.sessionId,
    enabled: status === 'in_progress',
    // 녹음·전사 중 끊기면 서버가 받던 오디오를 버린다. 같은 턴에 다시 답해야 한다(0007).
    onDrop: () => {
      recorderRef.current?.cancel();
      markRecording(id, null);
      setAnswer((prev) =>
        prev && (prev.phase === 'recording' || prev.phase === 'transcribing')
          ? { ...prev, phase: 'failed', failure: 'disconnected' }
          : prev,
      );
    },
    onMessage: (message) => {
      // 근거 확인 배너와 생성 중 표시는 다른 메시지를 받으면 내린다.
      if (message.type !== 'evidenceCheck') setEvidence(null);
      if (message.type !== 'thinking') setThinking(false);

      if (message.type === 'question') {
        // 녹음 중에 다른 턴 질문이 오면 그 녹음은 쓸 곳이 없다. 마이크를 닫는다.
        if (recordingTurnRef.current !== null && recordingTurnRef.current !== message.turn) {
          recorderRef.current?.cancel();
        }
        // 새 question이 오면 하던 녹음은 끝났다(다시 듣기 요청·녹음 취소). 표식을 남기면
        // 듣기 중 새로고침을 녹음 중 끊김으로 잘못 안내한다.
        markRecording(id, null);
        setLiveQuestion({
          persona: message.persona,
          text: message.text,
          turn: message.turn,
          mainIndex: message.mainIndex,
          followUpDepth: message.followUpDepth,
          audioUrl: message.audioUrl,
        });
        setPlayKey((key) => key + 1);
        setError(null);
        // 같은 턴이 다시 오면 다시 듣기다. 끊김 뒤 재연결로 다시 온 경우 실패 안내는 남긴다.
        setAnswer((prev) =>
          prev && prev.turn === message.turn && prev.phase === 'failed' ? prev : null,
        );
      } else if (message.type === 'transcriptPartial') {
        setAnswer((prev) =>
          prev &&
          prev.turn === message.turn &&
          (prev.phase === 'recording' || prev.phase === 'transcribing')
            ? { ...prev, partial: message.text }
            : prev,
        );
      } else if (message.type === 'transcript') {
        markRecording(id, null);
        setAnswer((prev) =>
          prev && prev.turn === message.turn
            ? { ...prev, phase: 'submitted', final: message.text, failure: null }
            : prev,
        );
      } else if (message.type === 'thinking') {
        setThinking(true);
      } else if (message.type === 'evidenceCheck') {
        setEvidence({ repository: message.repository, file: message.file });
      } else if (message.type === 'interviewEnd') {
        navigate(`/interview/${id}/report`, { replace: true });
      } else if (message.type === 'error') {
        if (message.reason === 'stt_failed') {
          fail(message.details?.cause === 'empty_transcript' ? 'empty' : 'stt');
          return;
        }
        if (message.reason === 'answer_rejected') {
          fail('rejected');
          return;
        }
        // 서버가 세션을 닫아 소켓 끊김(onDrop)으로 정리되지 않는다. 녹음·전사 중이던 답변은
        // 쓸 곳이 없으니 마이크를 닫고 표식과 상태를 지운다. 안내는 아래 오류 하나만 남긴다.
        if (!message.recoverable) {
          recorderRef.current?.cancel();
          markRecording(id, null);
          setAnswer((prev) =>
            prev && (prev.phase === 'recording' || prev.phase === 'transcribing') ? null : prev,
          );
        }
        setError({
          reason: message.reason,
          code: message.code,
          step: message.step,
          recoverable: message.recoverable,
          occurredAt: message.occurredAt,
        });
      }
      // answerReceived는 transcript 뒤에 오므로 화면이 따로 바꿀 것이 없다.
    },
  });

  const recorder = useAnswerRecorder({
    onStart: (mimeType) => {
      const turn = recordingTurnRef.current;
      if (turn === null) return;
      if (!send({ type: 'answerStart', turn, mimeType })) {
        recorderRef.current?.cancel();
        fail('disconnected');
        return;
      }
      markRecording(id, turn);
    },
    // 끊긴 동안 보내지 못한 조각은 버린다. 실패 처리는 onDrop이 한다.
    onChunk: (chunk) => void sendBinary(chunk),
    onStop: () => {
      const turn = recordingTurnRef.current;
      if (turn === null) return;
      if (!send({ type: 'answerEnd', turn })) {
        fail('disconnected');
        return;
      }
      setAnswer((prev) =>
        prev && prev.turn === turn && prev.phase === 'recording'
          ? { ...prev, phase: 'transcribing' }
          : prev,
      );
    },
    onMicLost: () => fail('micLost'),
    onError: () => fail('micUnavailable'),
  });

  useEffect(() => {
    recorderRef.current = recorder;
  });

  useEffect(() => {
    if (!evidence) return;
    const timer = setTimeout(() => setEvidence(null), EVIDENCE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [evidence]);

  /**
   * 새로고침·재연결 복구. 마지막 턴에 답변이 없으면 그게 지금 답할 질문이다.
   * 끊긴 사이 서버가 다음 턴으로 넘어갔을 수 있으므로 turn이 큰 쪽을 쓴다.
   * 스냅샷에는 질문 음성 주소가 없다 — 재연결 때 서버가 같은 턴 question을 다시 보내면 재생된다.
   */
  const turns = interview?.turns ?? [];
  const lastTurn = turns[turns.length - 1];
  const snapshotQuestion: LiveQuestion | null =
    lastTurn && lastTurn.answer === null
      ? {
          persona: lastTurn.persona,
          text: lastTurn.question,
          turn: lastTurn.turn,
          mainIndex: lastTurn.mainIndex,
          followUpDepth: lastTurn.followUpDepth,
          audioUrl: null,
        }
      : null;
  const question =
    snapshotQuestion && (!liveQuestion || snapshotQuestion.turn > liveQuestion.turn)
      ? snapshotQuestion
      : liveQuestion;

  const questionAudio = useQuestionAudio(question?.audioUrl ?? null, playKey);

  /** 지금 턴의 답변 상태. 턴이 바뀌면 듣기부터 시작한다. */
  const current: AnswerState =
    answer && question && answer.turn === question.turn
      ? answer
      : { turn: question?.turn ?? -1, phase: 'listening', partial: '', final: null, failure: null };

  /**
   * 소켓은 붙어 있는데 서버가 transcript를 보내지 않을 수 있다. 일정 시간 뒤 스냅샷으로
   * 그 턴이 저장됐는지 보고, 저장됐으면 제출 완료로, 아니면 끊김 실패로 돌린다.
   */
  useEffect(() => {
    if (current.phase !== 'transcribing') return;
    const turn = current.turn;
    const timer = setTimeout(() => {
      void refetchInterview().then(({ data, isError }) => {
        // 조회가 실패하면 캐시의 예전 값(answer: null)이 온다. 저장 여부를 모르므로
        // 끊김으로 단정하지 않고 다음 주기에 다시 확인한다.
        if (isError) {
          setRecheck((count) => count + 1);
          return;
        }
        const saved = data?.turns.find((entry) => entry.turn === turn)?.answer ?? null;
        markRecording(id, null);
        setAnswer((prev) =>
          prev && prev.turn === turn && prev.phase === 'transcribing'
            ? saved !== null
              ? { ...prev, phase: 'submitted', final: saved }
              : { ...prev, phase: 'failed', failure: 'disconnected' }
            : prev,
        );
      });
    }, TRANSCRIPT_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [current.phase, current.turn, refetchInterview, id, recheck]);

  /**
   * remainingSeconds는 서버 시각 기준이다. 응답을 받은 시점(dataUpdatedAt)부터
   * 흐른 만큼을 빼서 표시한다. 재연결로 GET을 다시 부르면 서버값으로 덮어써진다.
   */
  const remaining = interview
    ? Math.max(0, interview.remainingSeconds - Math.floor((now - dataUpdatedAt) / 1000))
    : null;

  /** recoverable: false면 서버가 세션을 닫는다. 더 보낼 수 없으므로 답변을 막는다. */
  const fatal = !!error && !error.recoverable;
  const canStart = !fatal && !!question && wsStatus === 'open' && current.phase === 'listening';
  const elapsedSeconds = recorder.startedAt
    ? Math.floor(Math.min(MAX_ANSWER_MS, now - recorder.startedAt) / 1000)
    : 0;
  const showText = showQuestionText || questionAudio.state === 'failed';

  /**
   * 조건부로 나타나는 요소에 aria-live를 달면 삽입 시점을 놓치는 조합이 있다.
   * 항상 떠 있는 영역 하나에 현재 상태를 넣어 변화만 읽히게 한다.
   */
  const liveStatus = error
    ? '' // 오류 배너가 role="alert"로 읽는다. 여기서 또 읽으면 두 번 들린다.
    : current.phase === 'recording'
      ? '녹음 중이에요'
      : current.phase === 'transcribing'
        ? '답변을 정리하고 있어요'
        : wsStatus === 'reconnecting'
          ? '연결이 끊겼어요. 다시 연결하는 중이에요'
          : thinking
            ? '다음 질문을 만들고 있어요'
            : '';

  function handleStartAnswer() {
    if (!question || !canStart) return;
    questionAudio.stop();
    recordingTurnRef.current = question.turn;
    setAnswer({ turn: question.turn, phase: 'recording', partial: '', final: null, failure: null });
    void recorder.start();
  }

  function handleRetryAnswer() {
    markRecording(id, null);
    setAnswer(null);
  }

  function handleLeave() {
    // 서버에 이탈을 알리지 않는다. 명세는 명시적 이탈만 abandoned로 인정하는데
    // (spec/frontend/features/interview.md:90, backend/docs/pipeline.md:241-242)
    // 알릴 수단이 계약에 없다 — REST 엔드포인트도, WS 클라이언트 메시지도, close code
    // 규약도 없다. 서버는 이 종료를 단순 끊김과 구분하지 못한다.
    // spec/shared/contracts/migration.md의 `명시적 이탈 통지` 행 참고 (PENDING_BE).
    setLeaveModalOpen(false);
    recorder.cancel();
    markRecording(id, null);
    closeSocket();
    navigate('/home', { replace: true });
  }

  if (interviewFailed) {
    return (
      <Shell me={me}>
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
        <h1 className="text-base font-bold">중단된 면접이에요</h1>
        <button
          type="button"
          onClick={() => navigate('/home')}
          className="h-12 rounded-lg bg-accent text-sm font-bold text-surface"
        >
          홈으로
        </button>
      </Shell>
    );
  }

  return (
    <Shell me={me} remaining={remaining}>
      <div className="flex justify-center gap-14">
        {PERSONA_ORDER.map((key) => {
          const speaking = question?.persona === key;
          return (
            <div key={key} className="flex flex-col items-center gap-2">
              {/* alt는 비운다. 바로 아래 라벨이 같은 이름을 읽어줘서 중복된다. */}
              <img
                src={PERSONA_IMAGES[key]}
                alt=""
                className={
                  speaking
                    ? 'h-20 w-20 rounded-full object-cover ring-2 ring-accent'
                    : 'h-20 w-20 rounded-full object-cover opacity-50 grayscale'
                }
              />
              <span
                className={speaking ? 'text-[13px] font-bold' : 'text-[13px] text-muted'}
                aria-current={speaking ? 'true' : undefined}
              >
                {speaking && '🔊 '}
                {PERSONA_LABELS[key]}
              </span>
            </div>
          );
        })}
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {liveStatus}
      </p>

      {wsStatus === 'reconnecting' && (
        <p className="text-[11px] font-bold text-error">연결이 끊겼어요 · 다시 연결하는 중이에요</p>
      )}

      {thinking && !evidence && <p className="text-[11px] text-muted">다음 질문을 만들고 있어요</p>}

      {evidence && (
        <p className="rounded-card bg-accent-soft px-3 py-2 text-[11px] text-accent">
          근거 확인 중 · {evidence.repository} / {evidence.file}
        </p>
      )}

      <div className="rounded-card border border-line-soft p-5">
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-accent-soft px-3 py-1 text-[11px] font-bold text-accent">
            {question
              ? `질문 ${question.turn}${interview?.totalTurns ? ` / ${interview.totalTurns}` : ''}${
                  question.followUpDepth > 0 ? ` · 꼬리질문 ${question.followUpDepth}` : ''
                } · ${PERSONA_LABELS[question.persona]}`
              : '다음 질문 준비 중'}
          </span>
          <span className="flex-1" />
          <label className="flex items-center gap-2">
            <span className="text-[11px] text-muted">질문 텍스트</span>
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
        </div>

        {showText ? (
          <>
            <p className="mt-4 text-[17px] font-bold leading-relaxed">
              {question?.text ?? '다음 질문을 준비하고 있어요'}
            </p>
            {/* 텍스트를 꺼 뒀는데 보이는 이유를 알린다. 토글이 고장 난 것처럼 보이지 않게 한다. */}
            {!showQuestionText && question && (
              <p className="mt-2 text-[11px] text-muted">
                질문 음성을 재생하지 못해 텍스트로 보여드려요
              </p>
            )}
          </>
        ) : (
          <p className="mt-4 text-[17px] font-bold leading-relaxed text-muted">
            {questionAudio.state === 'playing'
              ? '🔊 질문을 들려드리고 있어요'
              : '질문 텍스트를 숨겼어요'}
          </p>
        )}
      </div>

      {/* 다시 듣기 버튼 대신 음성으로 요청하게 안내한다. 좁은 화면에서는 질문 아래에 놓인다.
          넓은 화면에서는 본문(max-w-3xl, 768px) 오른쪽에 24px 띄워 고정한다. */}
      <aside className="rounded-card bg-accent-soft px-4 py-3 text-[12px] leading-relaxed text-accent xl:fixed xl:left-[calc(50%+408px)] xl:top-1/3 xl:w-52">
        <b>Tip</b>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {TIPS.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      </aside>

      {error && (
        <div role="alert" className="rounded-card border border-error/30 bg-error-soft px-3 py-2.5">
          <p className="text-[12px] font-bold text-error">
            {ERROR_MESSAGE[error.reason] ?? '면접 중 문제가 생겼어요.'}
          </p>
          <p className="mt-1 text-[11px] text-muted">
            {error.code} · {error.occurredAt}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-[11px] text-muted">내 답변</p>
        <div
          className={`min-h-[120px] rounded-card border px-4 py-3.5 text-[14px] leading-relaxed ${
            current.phase === 'recording' ? 'border-error' : 'border-line-soft'
          }`}
        >
          {current.final !== null ? (
            <>
              <span data-testid="transcript-final">{current.final}</span>
              <span className="mt-2 block text-[11px] text-muted">최종 전사로 평가해요</span>
            </>
          ) : current.partial ? (
            <span
              data-testid="transcript-partial"
              className={current.phase === 'transcribing' ? 'text-muted opacity-60' : 'text-muted'}
            >
              {current.partial}
            </span>
          ) : (
            <span className="text-muted">
              {!question
                ? '질문을 기다리고 있어요'
                : current.phase === 'recording'
                  ? '듣고 있어요…'
                  : current.phase === 'listening'
                    ? '답변 시작을 누르고 말해주세요'
                    : ''}
            </span>
          )}
        </div>

        {current.phase === 'transcribing' && (
          <p className="text-[11px] text-muted">답변을 정리하고 있어요…</p>
        )}

        {current.phase === 'failed' && current.failure && (
          <p role="alert" className="text-[11px] font-bold text-error">
            {FAILURE_MESSAGE[current.failure]}
          </p>
        )}

        <div className="flex items-center gap-3">
          {current.phase === 'recording' && (
            <span
              role="status"
              className="flex items-center gap-1.5 text-[11px] font-bold text-error"
            >
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-error" />
              녹음 중 {formatRemaining(elapsedSeconds)} / {formatRemaining(MAX_ANSWER_MS / 1000)}
            </span>
          )}
          <span className="flex-1" />
          {fatal ? (
            /*
              recoverable: false의 복구 경로는 reason마다 다르다
              (spec/frontend/features/interview.md:201-202). 홈으로만 보내면 같은 오류를
              다시 만난다. 레포 재선택은 새 세션을 만들고 이 세션은 abandoned가 된다(:64).
            */
            error?.reason === 'github_token_invalid' ? (
              <a
                href={`${BASE}/auth/github/link`}
                className="flex h-10 items-center rounded-lg bg-accent px-5 text-[13px] font-bold text-surface"
              >
                GitHub 다시 연동하기
              </a>
            ) : error?.reason === 'repo_unreachable' && interview ? (
              <button
                type="button"
                onClick={() => navigate(`/interview/repos/${interview.runId}`)}
                className="h-10 rounded-lg bg-accent px-5 text-[13px] font-bold text-surface"
              >
                레포 다시 선택하기
              </button>
            ) : (
              <button
                type="button"
                onClick={() => navigate('/home')}
                className="h-10 rounded-lg bg-accent px-5 text-[13px] font-bold text-surface"
              >
                홈으로
              </button>
            )
          ) : current.phase === 'recording' ? (
            <button
              type="button"
              disabled={!recorder.canStop}
              onClick={recorder.stop}
              className="h-10 rounded-lg bg-error-soft px-5 text-[13px] font-bold text-error disabled:opacity-50"
            >
              답변 끝내기
            </button>
          ) : current.phase === 'failed' ? (
            <button
              type="button"
              onClick={handleRetryAnswer}
              className="h-10 rounded-lg bg-accent-soft px-5 text-[13px] font-bold text-accent"
            >
              다시 답변하기
            </button>
          ) : current.phase === 'listening' ? (
            <button
              type="button"
              disabled={!canStart}
              onClick={handleStartAnswer}
              className="h-10 rounded-lg bg-accent-soft px-5 text-[13px] font-bold text-accent disabled:bg-line-soft disabled:text-muted"
            >
              답변 시작
            </button>
          ) : null}
        </div>
      </div>

      {/* 이미 종료된 세션이면 확인할 게 없다. 모달 없이 바로 나간다. */}
      {!fatal && (
        <button
          type="button"
          onClick={() => setLeaveModalOpen(true)}
          className="h-12 rounded-lg border border-line text-sm font-bold text-muted"
        >
          면접 종료
        </button>
      )}

      {/*
        네이티브 dialog를 쓴다. showModal()이 Esc 닫기·포커스 가둠·배경 inert·
        스크롤 잠금을 브라우저 쪽에서 처리해 준다. 직접 구현할 이유가 없다.
      */}
      <dialog
        ref={leaveDialogRef}
        onClose={() => setLeaveModalOpen(false)}
        className="rounded-card bg-surface p-5 text-ink backdrop:bg-ink/40"
      >
        <div className="flex w-[300px] max-w-full flex-col gap-3">
          <h2 className="text-[15px] font-bold">면접을 종료할까요?</h2>
          <p className="text-[12px] text-muted">
            지금 나가면 면접이 중단돼요. 중단된 면접은 리포트가 만들어지지 않아요.
          </p>
          <div className="mt-1 flex gap-2">
            <button
              type="button"
              autoFocus
              onClick={() => setLeaveModalOpen(false)}
              className="h-10 flex-1 rounded-lg border border-line text-[13px] font-bold"
            >
              계속하기
            </button>
            <button
              type="button"
              onClick={handleLeave}
              className="h-10 flex-1 rounded-lg bg-error text-[13px] font-bold text-surface"
            >
              종료하기
            </button>
          </div>
        </div>
      </dialog>
    </Shell>
  );
}

function Shell({
  me,
  remaining,
  children,
}: {
  me?: MeResponse;
  remaining?: number | null;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header
        active="interview"
        name={me?.name}
        avatarUrl={me?.avatarUrl ?? undefined}
        statusSlot={
          remaining != null ? (
            <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
              잔여 {formatRemaining(remaining)}
            </span>
          ) : undefined
        }
      />
      <main className="flex flex-1 flex-col items-center justify-center px-7 py-6">
        <div className="flex w-full max-w-3xl flex-col gap-5">{children}</div>
      </main>
      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>면접 중에는 페이지를 벗어나지 마세요</span>
      </footer>
    </div>
  );
}
