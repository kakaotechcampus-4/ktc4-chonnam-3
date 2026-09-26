import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { BASE, api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import { PERSONA_IMAGES, PERSONA_LABELS, PERSONA_ORDER } from '@/shared/persona';
import { useInterviewSocket } from '@/features/interview/useInterviewSocket';
import { QUESTION_TEXT_KEY, readQuestionText } from '@/features/interview/questionText';
import type { InterviewLastError, MeResponse, Persona } from '@/types/api';

const ANSWER_MAX_LENGTH = 2000;

/** 진행 중 오류 문구. 준비 단계 오류는 5a2-v2가 처리하므로 여기서는 다루지 않는다. */
const ERROR_MESSAGE: Record<string, string> = {
  answer_too_long: '답변이 너무 길어요. 2000자 이내로 줄여서 다시 보내주세요.',
  answer_rejected: '답변을 저장하지 못했어요. 다시 보내주세요.',
  answer_stale_turn: '지난 질문에 대한 답변이에요. 현재 질문에 다시 답해주세요.',
  question_failed: '다음 질문을 만들지 못했어요. 잠시만 기다려주세요.',
  repo_unreachable: '레포에 접근할 수 없어 면접을 이어갈 수 없어요.',
  github_token_invalid: 'GitHub 연동이 만료돼 면접을 이어갈 수 없어요.',
};

/** 30초간 다른 메시지가 없으면 근거 확인 배너를 내린다. */
const EVIDENCE_TIMEOUT_MS = 30_000;

/** 이 간격으로 answerReceived가 없는 턴의 저장 여부를 다시 확인한다. */
const ACK_RECHECK_MS = 30_000;

function formatRemaining(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
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

  const [liveQuestion, setLiveQuestion] = useState<{
    persona: Persona;
    text: string;
    turn: number;
  } | null>(null);
  /**
   * 잠금은 메시지가 아니라 턴 번호로 판단한다. 연결이 끊긴 사이 온 question을
   * 놓쳐도 스냅샷으로 turn이 바뀌면 입력창이 저절로 열린다.
   */
  const [submittedTurn, setSubmittedTurn] = useState<number | null>(null);
  /** answerReceived로 확인된 턴. submittedTurn과 다르면 아직 수신 확인 전이다. */
  const [ackedTurn, setAckedTurn] = useState<number | null>(null);
  /**
   * 제출한 턴의 동기 사본. answerReceived가 리렌더보다 먼저 도착해도
   * 핸들러가 낡은 값을 읽지 않게 한다.
   */
  const submittedTurnRef = useRef<number | null>(null);
  const [thinking, setThinking] = useState(false);
  /** 초안도 턴에 묶는다. 턴이 바뀌면 이전 턴 초안은 버린다. */
  const [draft, setDraft] = useState({ turn: -1, text: '' });
  const [evidence, setEvidence] = useState<{ repository: string; file: string } | null>(null);
  /** 연결이 끊겨 답변을 보내지 못했다. 재연결되면 다시 누르면 된다. */
  const [sendFailed, setSendFailed] = useState(false);
  /** 답변을 보낸 시점의 표식. 그 뒤에 끊겼는지, 서버가 저장했는지 판단한다. */
  const [sentMark, setSentMark] = useState<{ at: number; drops: number } | null>(null);
  /** ack을 기다리며 스냅샷을 다시 받아본 횟수. 0보다 크면 끊김과 같게 취급한다. */
  const [ackAttempt, setAckAttempt] = useState(0);
  const [error, setError] = useState<InterviewLastError | null>(null);
  const [leaveModalOpen, setLeaveModalOpen] = useState(false);
  const leaveDialogRef = useRef<HTMLDialogElement>(null);
  const [showQuestionText, setShowQuestionText] = useState(readQuestionText);
  /** 1초마다 흐르는 시계. 남은 시간은 서버 스냅샷과 이 값으로 계산한다. */
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

  const {
    wsStatus,
    dropCount,
    send,
    close: closeSocket,
  } = useInterviewSocket({
    interviewId: id,
    sessionId: interview?.sessionId,
    enabled: status === 'in_progress',
    onMessage: (message) => {
      // 근거 확인 배너와 생성 중 표시는 다른 메시지를 받으면 내린다.
      if (message.type !== 'evidenceCheck') setEvidence(null);
      if (message.type !== 'thinking') setThinking(false);

      if (message.type === 'question') {
        setLiveQuestion({ persona: message.persona, text: message.text, turn: message.turn });
        setError(null);
        setSendFailed(false);
      } else if (message.type === 'answerReceived') {
        // 제출 중 표시만 푼다. 입력창은 다음 턴이 와야 열린다.
        // 재연결 직후 서버가 지난 턴 ack을 다시 보내면 ref가 비어 있을 수 있다.
        // 그때 null로 덮으면 이미 확인된 턴이 다시 미확인으로 뒤집힌다.
        if (submittedTurnRef.current !== null) setAckedTurn(submittedTurnRef.current);
      } else if (message.type === 'thinking') {
        setThinking(true);
      } else if (message.type === 'evidenceCheck') {
        setEvidence({ repository: message.repository, file: message.file });
      } else if (message.type === 'interviewEnd') {
        navigate(`/interview/${id}/report`, { replace: true });
      } else if (message.type === 'error') {
        setError({
          reason: message.reason,
          code: message.code,
          step: message.step,
          recoverable: message.recoverable,
          occurredAt: message.occurredAt,
        });
        // 같은 턴에 다시 제출할 수 있는 오류면 그 턴의 잠금을 푼다.
        if (message.recoverable && message.reason.startsWith('answer_')) {
          submittedTurnRef.current = null;
          setSubmittedTurn(null);
        }
        // 지나간 턴에 보낸 답변이다. 그 초안은 되살릴 곳이 없으므로 버리고,
        // 서버가 보고 있는 현재 질문을 스냅샷으로 다시 받는다. api-spec.md #18.
        if (message.reason === 'answer_stale_turn') {
          setDraft({ turn: -1, text: '' });
          void refetchInterview();
        }
      }
    },
  });

  useEffect(() => {
    if (!evidence) return;
    const timer = setTimeout(() => setEvidence(null), EVIDENCE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [evidence]);

  /**
   * 새로고침·재연결 복구. 마지막 턴에 답변이 없으면 그게 지금 답할 질문이다.
   * 끊긴 사이 서버가 다음 턴으로 넘어갔을 수 있으므로 turn이 큰 쪽을 쓴다.
   * liveQuestion만 믿으면 재연결 후 지난 질문에 답하게 된다.
   */
  const turns = interview?.turns ?? [];
  const lastTurn = turns[turns.length - 1];
  const snapshotQuestion =
    lastTurn && lastTurn.answer === null
      ? { persona: lastTurn.persona, text: lastTurn.question, turn: lastTurn.turn }
      : null;
  const question =
    snapshotQuestion && (!liveQuestion || snapshotQuestion.turn > liveQuestion.turn)
      ? snapshotQuestion
      : liveQuestion;

  /**
   * remainingSeconds는 서버 시각 기준이다. 응답을 받은 시점(dataUpdatedAt)부터
   * 흐른 만큼을 빼서 표시한다. 재연결로 GET을 다시 부르면 서버값으로 덮어써진다.
   */
  const remaining = interview
    ? Math.max(0, interview.remainingSeconds - Math.floor((now - dataUpdatedAt) / 1000))
    : null;

  /** recoverable: false면 서버가 세션을 닫는다. 더 보낼 수 없으므로 입력을 막는다. */
  const fatal = !!error && !error.recoverable;
  const answerDraft = draft.turn === question?.turn ? draft.text : '';
  /**
   * 제출한 턴의 스냅샷. 마지막 턴이 아니라 제출한 턴을 직접 찾는다 — 서버가 저장하고
   * 다음 턴으로 넘어간 경우에도 마지막 턴은 answer가 null이라 오판한다.
   */
  const submittedEntry =
    submittedTurn === null ? undefined : turns.find((entry) => entry.turn === submittedTurn);
  /**
   * 스냅샷에 그 턴 답변이 있으면 서버가 저장한 것이다. answerReceived를 놓쳤어도
   * 확인된 것과 같게 본다. 그러지 않으면 "전송 중..." 표시가 다음 질문까지 남는다.
   */
  const ackedBySnapshot = submittedEntry?.answer != null;
  const pendingAck =
    submittedTurn !== null && submittedTurn !== ackedTurn && !ackedBySnapshot;

  /**
   * 소켓이 끊기지 않아도 서버가 응답을 멈출 수 있다. 그때는 dropCount가 오르지 않아
   * 재연결도 GET도 일어나지 않고 입력창이 잠긴 채로 남는다. ack을 기다리는 동안
   * 스냅샷을 주기적으로 다시 받아 그 턴이 저장됐는지 확인한다. 조회가 실패해도
   * ackAttempt가 올라 다음 주기가 예약되므로 판단 기회를 잃지 않는다.
   * 자동 재전송은 하지 않는다.
   */
  useEffect(() => {
    if (!pendingAck || sentMark === null) return;
    const timer = setTimeout(() => {
      void refetchInterview().finally(() => setAckAttempt((count) => count + 1));
    }, ACK_RECHECK_MS);
    return () => clearTimeout(timer);
  }, [pendingAck, sentMark, refetchInterview, ackAttempt]);
  const overLength = answerDraft.length > ANSWER_MAX_LENGTH;

  /**
   * 보낸 뒤 연결이 끊겼거나 응답이 없었고, 그 뒤 받은 스냅샷에도 "그 턴"의 답변이 없다.
   * 이미 다음 턴으로 넘어갔다면 되돌릴 게 없으므로 같은 턴일 때만 권한다.
   * 자동 재전송은 하지 않는다. 다른 턴으로 간 답은 서버가 answer_stale_turn으로 거르지만,
   * 같은 턴에서 첫 요청이 늦게 처리되는 경합은 계약에 규칙이 없다 — 어느 답을 저장할지,
   * 중복을 무엇으로 알릴지 정해지지 않았다. migration.md의 `같은 턴 중복 답변` 행 참고
   * (PENDING_BE).
   */
  const ackLost =
    pendingAck &&
    submittedTurn === question?.turn &&
    sentMark !== null &&
    (dropCount > sentMark.drops || ackAttempt > 0) &&
    dataUpdatedAt > sentMark.at &&
    submittedEntry?.answer === null;

  // 전달 실패가 확인되면 고쳐서 다시 보낼 수 있게 잠금을 푼다.
  const locked = fatal || !question || (submittedTurn === question.turn && !ackLost);
  const submitting = pendingAck && submittedTurn === question?.turn && !ackLost;
  const canSubmit = !locked && answerDraft.trim() !== '' && !overLength;

  /** 재연결되면 실패 안내를 내린다. 다시 누를 수 있는 상태가 됐다는 뜻이다. */
  const showSendFailed = sendFailed && wsStatus !== 'open';

  /**
   * 다른 안내를 덮어야 하는 오류. answer_stale_turn은 이미 지나간 턴에 대한 안내라
   * 현재 상황을 가리면 안 된다 — 그 뒤에 생긴 전송 실패가 묻힌다.
   */
  const blockingError = error && error.reason !== 'answer_stale_turn' ? error : null;

  /**
   * 조건부로 나타나는 요소에 aria-live를 달면 삽입 시점을 놓치는 조합이 있다.
   * 항상 떠 있는 영역 하나에 현재 상태를 넣어 변화만 읽히게 한다.
   */
  const liveStatus = blockingError
    ? '' // 오류 배너가 role="alert"로 읽는다. 여기서 또 읽으면 두 번 들린다.
    : ackLost
      ? '답변이 전달되지 못했어요. 고쳐서 다시 보낼 수 있어요'
      : showSendFailed
        ? '연결이 끊겨 답변을 보내지 못했어요'
        : wsStatus === 'reconnecting'
          ? '연결이 끊겼어요. 다시 연결하는 중이에요'
          : thinking
            ? '다음 질문을 만들고 있어요'
            : '';

  function handleSubmit() {
    // 첫 제출과 재전송이 같은 경로를 쓴다. 버튼 disabled와 별개로 내용을 한 번 더 본다.
    if (!question || answerDraft.trim() === '' || overLength) return;

    setError(null);
    // 연결이 없으면 큐에 담지 않고 실패로 돌린다 — 사유는 useInterviewSocket의 send.
    if (!send({ type: 'answer', turn: question.turn, text: answerDraft })) {
      // 보내지 못했으니 제출한 적 없는 상태로 되돌린다. 입력창과 초안이 유지된다.
      setSendFailed(true);
      submittedTurnRef.current = null;
      setSubmittedTurn(null);
      return;
    }

    setSendFailed(false);
    setAckAttempt(0);
    setSentMark({ at: Date.now(), drops: dropCount });
    submittedTurnRef.current = question.turn;
    setSubmittedTurn(question.turn);
  }

  function handleLeave() {
    // 서버에 이탈을 알리지 않는다. 명세는 명시적 이탈만 abandoned로 인정하는데
    // (spec/frontend/features/interview.md:90, backend/docs/pipeline.md:241-242)
    // 알릴 수단이 계약에 없다 — REST 엔드포인트도, WS 클라이언트 메시지도, close code
    // 규약도 없다. 서버는 이 종료를 단순 끊김과 구분하지 못한다.
    // spec/shared/contracts/migration.md의 `명시적 이탈 통지` 행 참고 (PENDING_BE).
    setLeaveModalOpen(false);
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
              ? `질문 ${question.turn}${interview?.totalTurns ? ` / ${interview.totalTurns}` : ''} · ${PERSONA_LABELS[question.persona]}`
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

        {showQuestionText ? (
          <p className="mt-4 text-[17px] font-bold leading-relaxed">
            {question?.text ?? '다음 질문을 준비하고 있어요'}
          </p>
        ) : (
          <p className="mt-4 text-[17px] font-bold leading-relaxed text-muted">
            질문 텍스트를 숨겼어요
          </p>
        )}
      </div>

      {ackLost && !blockingError && (
        <p className="text-[11px] font-bold text-error">
          답변이 전달되지 못했어요 · 고쳐서 다시 보낼 수 있어요
        </p>
      )}

      {showSendFailed && !ackLost && !blockingError && (
        <p className="text-[11px] font-bold text-error">
          연결이 끊겨 답변을 보내지 못했어요 · 다시 연결되면 한 번 더 눌러주세요
        </p>
      )}

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
        <textarea
          aria-label="답변"
          value={answerDraft}
          onChange={(event) =>
            question && setDraft({ turn: question.turn, text: event.target.value })
          }
          disabled={locked}
          placeholder={
            fatal
              ? '면접을 이어갈 수 없어요'
              : !question
                ? '질문을 기다리고 있어요'
                : !showQuestionText
                  ? '질문 텍스트를 숨긴 상태예요'
                  : !locked
                    ? '답변을 입력해주세요'
                    : '답변을 전송했어요 · 다음 질문을 기다리고 있어요'
          }
          rows={6}
          className="w-full resize-none rounded-card border border-line-soft px-4 py-3.5 text-[14px] outline-none placeholder:text-muted focus:border-accent disabled:bg-paper"
        />
        <div className="flex items-center gap-3">
          <span
            className={overLength ? 'text-[11px] font-bold text-error' : 'text-[11px] text-muted'}
          >
            {answerDraft.length} / {ANSWER_MAX_LENGTH}
          </span>
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
          ) : ackLost ? (
            <button
              type="button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="h-10 rounded-lg bg-accent px-5 text-[13px] font-bold text-surface disabled:bg-line-soft disabled:text-muted"
            >
              다시 보내기
            </button>
          ) : (
            <button
              type="button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="h-10 rounded-lg bg-accent px-5 text-[13px] font-bold text-surface disabled:bg-line-soft disabled:text-muted"
            >
              {submitting ? '전송 중...' : '답변 제출'}
            </button>
          )}
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
